BEGIN TRANSACTION;

-- NOTE: This is purely for local testing.
-- For creating real users, use:
--   flask --app app create-user

DELETE FROM listing_score_history;
DELETE FROM listing_price_history;
DELETE FROM listings;
DELETE FROM sqlite_sequence;

INSERT INTO listings (
    source, external_id, url, title,
    brand, model, variant,
    year, mileage_km, price_eur,
    fuel_type, transmission, color,
    accident, condition,
    raw_json
) VALUES
(
    'sample', 'S-1001', 'https://example.com/listing/1001', 'BMW 320d Touring',
    'BMW', '3er', '320d Touring',
    2018, 89000, 21900,
    'diesel', 'automatik', 'grau',
    0, 'gut',
    '{"note": "sample"}'
),
(
    'sample', 'S-1002', 'https://example.com/listing/1002', 'Audi A4 Avant 2.0 TDI',
    'Audi', 'A4', 'Avant 2.0 TDI',
    2016, 145000, 14900,
    'diesel', 'schalter', 'schwarz',
    0, 'ok',
    '{"note": "sample"}'
);

INSERT INTO listing_price_history (listing_id, price_eur, mileage_km)
SELECT id, price_eur, mileage_km FROM listings;

COMMIT;
