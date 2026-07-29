-- Providers
INSERT INTO dim_provider_lookup (
    provider_id,
    provider_name,
    specialty
)
VALUES
    (101, 'Provider A', 'Cardiology'),
    (102, 'Provider B', 'Neurology'),
    (103, 'Provider C', 'Orthopedics'),
    (104, 'Provider D', 'Primary Care'),
    (105, 'Provider E', 'Dermatology');

-- Events
INSERT INTO staging_events (
    event_id,
    provider_id,
    event_type,
    status,
    event_timestamp
)
VALUES
    (1, 101, 'AUTHORIZATION', 'APPROVED', '2026-07-20 08:30:00'),
    (2, 101, 'AUTHORIZATION', 'DENIED',   '2026-07-20 09:15:00'),
    (3, 102, 'CLAIM',         'COMPLETE', '2026-07-20 10:00:00'),
    (4, 103, 'AUTHORIZATION', 'APPROVED', '2026-07-21 11:30:00'),
    (5, 104, 'CLAIM',         'COMPLETE', '2026-07-21 12:00:00'),
    (6, 101, 'CLAIM',         'COMPLETE', '2026-07-22 08:00:00'),
    (7, 102, 'AUTHORIZATION', 'DENIED',   '2026-07-22 09:45:00'),
    (8, 103, 'CLAIM',         'COMPLETE', '2026-07-22 14:20:00'),
    (9, 104, 'AUTHORIZATION', 'APPROVED', '2026-07-23 07:30:00'),
    (10, 105, 'CLAIM',        'COMPLETE', '2026-07-23 16:10:00');