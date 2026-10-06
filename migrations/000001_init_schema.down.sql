-- 1. Удаляем индексы и таблицу swaps (так как она ссылается на pools)
DROP INDEX IF EXISTS idx_swaps_pool_time;
DROP INDEX IF EXISTS uq_swap_event;
DROP TABLE IF EXISTS swaps;

-- 2. Удаляем индексы и таблицу pools (так как она ссылается на tokens)
DROP INDEX IF EXISTS idx_pools_token1;
DROP INDEX IF EXISTS idx_pools_token0;
DROP TABLE IF EXISTS pools;

-- 3. Удаляем индексы и таблицу tokens (от нее больше никто не зависит)
DROP INDEX IF EXISTS idx_tokens_symbol;
DROP TABLE IF EXISTS tokens;
