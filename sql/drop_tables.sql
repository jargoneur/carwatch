BEGIN TRANSACTION;

DROP TABLE IF EXISTS saved_cars;
DROP TABLE IF EXISTS model_year_stats;
DROP TABLE IF EXISTS listing_score_history;
DROP TABLE IF EXISTS listing_price_history;
DROP TABLE IF EXISTS listings;
DROP TABLE IF EXISTS users;

COMMIT;
