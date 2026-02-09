-- Add alpha/beta pseudo-counts for Bayesian confidence with magnitude-weighted updates.
-- Backfills from legacy fire/success counts while handling known inconsistent rows where
-- success_count may exceed fire_count by flooring beta at the prior.

ALTER TABLE heuristics
    ADD COLUMN alpha DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    ADD COLUMN beta  DOUBLE PRECISION NOT NULL DEFAULT 1.0;

ALTER TABLE heuristics
    ADD CONSTRAINT chk_heuristics_alpha_positive CHECK (alpha > 0),
    ADD CONSTRAINT chk_heuristics_beta_positive CHECK (beta > 0);

UPDATE heuristics
SET alpha = 1.0 + success_count,
    beta = GREATEST(1.0, 1.0 + fire_count - success_count);

UPDATE heuristics
SET confidence = alpha / (alpha + beta);
