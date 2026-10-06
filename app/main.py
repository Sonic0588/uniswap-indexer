import asyncio
import os

import asyncpg
from dotenv import load_dotenv
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider


load_dotenv()

# Настройки (Замените на свои или вынесите в .env)
RPC_URL = os.getenv("RPC_URL", "https://base.org")  # Публичная нода Base
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/crypto_db")

# Контракт Фабрики Uniswap V2 на Base (у PancakeSwap/SushiSwap адреса будут другие)
UNISWAP_V2_FACTORY = "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6"

# Минимальный ABI Фабрики для трекинга события PairCreated
FACTORY_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "token0", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "token1", "type": "address"},
            {"indexed": False, "internalType": "address", "name": "pair", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "", "type": "uint256"},
        ],
        "name": "PairCreated",
        "type": "event",
    }
]

# Минимальный ABI токена ERC-20 для получения метаданных
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
]


async def get_or_create_token(w3, pool, token_address: str) -> None:
    """Проверяет наличие токена в БД, если нет — запрашивает из блокчейна и сохраняет"""
    token_address = token_address.lower()

    # Проверяем в базе
    exists = await pool.fetchval("SELECT 1 FROM tokens WHERE address = $1", token_address)
    if exists:
        return

    # Если токена нет, делаем RPC-запросы к контракту токена
    token_contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=ERC20_ABI)
    try:
        # Запускаем три запроса параллельно для экономии времени
        name, symbol, decimals = await asyncio.gather(
            token_contract.functions.name().call(),
            token_contract.functions.symbol().call(),
            token_contract.functions.decimals().call(),
        )
    except Exception:
        # Некоторые "скам-токены" ломают стандарты ERC-20, ставим дефолтные значения
        name, symbol, decimals = "Unknown Token", "UNKNOWN", 18

    # Сохраняем в Postgres
    await pool.execute(
        """
        INSERT INTO tokens (address, symbol, name, decimals)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (address) DO NOTHING
        """,
        token_address,
        symbol[:20],
        name[:100],
        decimals,
    )
    print(f"🆕 Индексирован новый токен: {symbol} ({token_address})")


async def handle_pair_created(w3, pool, event) -> None:
    """Обработка события создания новой торговой пары (пула)"""
    args = event["args"]
    pool_address = args["pair"].lower()
    token0 = args["token0"].lower()
    token1 = args["token1"].lower()
    block_number = event["blockNumber"]
    tx_hash = event["transactionHash"].hex()

    # 1. Гарантируем, что оба токена есть в нашей базе данных
    await get_or_create_token(w3, pool, token0)
    await get_or_create_token(w3, pool, token1)

    # 2. Сохраняем сам пул
    await pool.execute(
        """
        INSERT INTO pools (pool_address, token0_address, token1_address, fee_tier, block_number, tx_hash)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (pool_address) DO NOTHING
        """,
        pool_address,
        token0,
        token1,
        3000,
        block_number,
        tx_hash,  # 3000 (0.3%) дефолт для V2
    )
    print(f"📊 Добавлен новый пул: {pool_address} | Block: {block_number}")


async def main():
    # Инициализация асинхронного подключения к БД
    db_pool = await asyncpg.create_pool(DATABASE_URL)

    # Инициализация асинхронного Web3 клиента
    w3 = AsyncWeb3(AsyncHTTPProvider(RPC_URL))

    if await w3.is_connected():
        print(f"✅ Успешно подключено к RPC блокчейна: {RPC_URL}")
    else:
        print("❌ Ошибка подключения к RPC")
        return

    factory_contract = w3.eth.contract(address=w3.to_checksum_address(UNISWAP_V2_FACTORY), abi=FACTORY_ABI)

    # Определяем, с какого блока начать (можно взять текущий блок минус 100 для теста)
    current_block = await w3.eth.block_number
    from_block = current_block
    print(f"Запуск сканирования фабрики с блока {from_block}...")

    BLOCK_CHUNK_SIZE = 20

    while True:
        try:
            to_block = await w3.eth.block_number
            if from_block > to_block:
                await asyncio.sleep(2)  # Ждем появления новых блоков
                continue

            # Ограничиваем шаг, чтобы публичная нода не выдала ошибку "too many logs"
            step = min(from_block + BLOCK_CHUNK_SIZE, to_block)

            # Запрашиваем логи исторических событий
            events = await factory_contract.events.PairCreated.get_logs(from_block=from_block, to_block=step)

            for event in events:
                await handle_pair_created(w3, db_pool, event)

            from_block = step + 1
            await asyncio.sleep(1)  # Небольшая пауза, чтобы не спамить ноду

        except Exception as e:
            print(
                f"⚠️ Ошибка в цикле индексации на блоках {from_block}-{step if 'step' in locals() else 'unknown'}: {e}"
            )
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
