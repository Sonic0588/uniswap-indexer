CREATE TABLE IF NOT EXISTS tokens (
    address VARCHAR(42) PRIMARY KEY,      -- Адрес контракта токена (0x...) в нижнем регистре
    symbol VARCHAR(20) NOT NULL,          -- Тикер (например, WETH, USDC)
    name VARCHAR(100) NOT NULL,           -- Полное название токена
    decimals SMALLINT NOT NULL,           -- Важнейшее поле для расчетов (обычно 6 или 18)
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для быстрого поиска токена по тикеру
CREATE INDEX idx_tokens_symbol ON tokens(symbol);

CREATE TABLE IF NOT EXISTS pools (
    pool_address VARCHAR(42) PRIMARY KEY, -- Адрес самого контракта пула
    token0_address VARCHAR(42) REFERENCES tokens(address), -- Токен 0 (всегда меньший адрес по алфавиту)
    token1_address VARCHAR(42) REFERENCES tokens(address), -- Токен 1
    fee_tier INT NOT NULL,                -- Комиссия пула (для V3: например, 500, 3000, 10000)
    block_number BIGINT NOT NULL,         -- Номер блока, в котором создан пул
    tx_hash VARCHAR(66) NOT NULL,         -- Хэш транзакции создания
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для быстрого поиска пулов по конкретному токену
CREATE INDEX idx_pools_token0 ON pools(token0_address);
CREATE INDEX idx_pools_token1 ON pools(token1_address);

CREATE TABLE IF NOT EXISTS swaps (
    id BIGSERIAL PRIMARY KEY,             -- Внутренний ID
    pool_address VARCHAR(42) REFERENCES pools(pool_address),
    block_number BIGINT NOT NULL,         -- Номер блока (нужен для сортировки и валидации)
    tx_hash VARCHAR(66) NOT NULL,         -- Хэш транзакции (для линковки с эксплорерами)
    log_index INT NOT NULL,               -- Индекс лога внутри блока (защита от дублей, если в одной tx несколько свопов)
    
    -- Сырые значения из блокчейна (всегда сохраняйте их «как есть» для аудита)
    amount0_raw NUMERIC(78, 0) NOT NULL,  -- В Web3 числа могут быть до 256 бит, используем NUMERIC
    amount1_raw NUMERIC(78, 0) NOT NULL,
    
    -- Декодированные «человеческие» значения (с учетом decimals, считает Python перед записью)
    amount0 FLOAT NOT NULL,               
    amount1 FLOAT NOT NULL,               
    
    timestamp TIMESTAMP NOT NULL          -- Время майнинга блока (берется из свойств блока)
);

-- Составной уникальный индекс, гарантирующий, что мы не запишем один своп дважды при сбоях сети
CREATE UNIQUE INDEX uq_swap_event ON swaps(block_number, tx_hash, log_index);
-- Индекс для построения графиков по времени и конкретному пулу
CREATE INDEX idx_swaps_pool_time ON swaps(pool_address, timestamp DESC);
