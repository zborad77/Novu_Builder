from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "prisma"
DB_PATH = DB_DIR / "dev.db"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ico TEXT,
    email TEXT,
    phone TEXT,
    default_currency TEXT NOT NULL DEFAULT 'CZK',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    company_name TEXT,
    email TEXT,
    phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pricing_profiles (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    name TEXT NOT NULL,
    hourly_rate REAL NOT NULL,
    daily_rate REAL NOT NULL,
    margin_economy_pct REAL NOT NULL,
    margin_standard_pct REAL NOT NULL,
    margin_premium_pct REAL NOT NULL,
    vat_pct REAL NOT NULL DEFAULT 21,
    currency TEXT NOT NULL DEFAULT 'CZK',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    client_id TEXT,
    created_by_user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    property_type TEXT,
    repair_scope TEXT,
    location_lat REAL,
    location_lng REAL,
    address_label TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS project_photos (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    width INTEGER,
    height INTEGER,
    taken_at TEXT,
    exif_lat REAL,
    exif_lng REAL,
    sort_order INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,
    job_type TEXT NOT NULL,
    requested_by_user_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    analysis_job_id TEXT,
    object_type TEXT,
    surface_condition TEXT,
    recommended_scope TEXT,
    estimated_area_sqm REAL,
    area_confidence REAL,
    mask_polygon_json TEXT,
    materials_suggestion_json TEXT,
    workflow_suggestion_json TEXT,
    model_name TEXT,
    model_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (analysis_job_id) REFERENCES analysis_jobs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS quote_variants (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    analysis_result_id TEXT,
    pricing_profile_id TEXT,
    variant_type TEXT NOT NULL,
    labor_cost REAL NOT NULL,
    material_cost REAL NOT NULL,
    other_cost REAL NOT NULL,
    margin_pct REAL NOT NULL,
    total_ex_vat REAL NOT NULL,
    vat_amount REAL NOT NULL,
    total_inc_vat REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (analysis_result_id) REFERENCES analysis_results(id) ON DELETE SET NULL,
    FOREIGN KEY (pricing_profile_id) REFERENCES pricing_profiles(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS quote_items (
    id TEXT PRIMARY KEY,
    quote_variant_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL,
    total_price REAL NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (quote_variant_id) REFERENCES quote_variants(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_projects_organization_id ON projects(organization_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_project_photos_project_id ON project_photos(project_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_project_id ON analysis_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_analysis_results_project_id ON analysis_results(project_id);
CREATE INDEX IF NOT EXISTS idx_quote_variants_project_id ON quote_variants(project_id);
CREATE INDEX IF NOT EXISTS idx_quote_items_quote_variant_id ON quote_items(quote_variant_id);
"""

SEED_SQL = """
INSERT OR IGNORE INTO organizations (
    id, name, ico, email, phone, default_currency
) VALUES (
    'org_1', 'NOVU Demo', '12345678', 'info@novu.local', '+420777000111', 'CZK'
);

INSERT OR IGNORE INTO users (
    id, organization_id, email, password_hash, full_name, role, is_active
) VALUES (
    'usr_1', 'org_1', 'demo@novu.local', 'demo-hash', 'Demo Manager', 'manager', 1
);

INSERT OR IGNORE INTO clients (
    id, organization_id, full_name, company_name, email, phone, notes
) VALUES (
    'cli_1', 'org_1', 'Petr Novak', '', 'petr.novak@example.com', '+420777111222', ''
);

INSERT OR IGNORE INTO pricing_profiles (
    id, organization_id, name, hourly_rate, daily_rate, margin_economy_pct,
    margin_standard_pct, margin_premium_pct, vat_pct, currency, is_default
) VALUES (
    'price_default', 'org_1', 'Default profile', 520, 4200, 12, 18, 28, 21, 'CZK', 1
);

INSERT OR IGNORE INTO projects (
    id, organization_id, client_id, created_by_user_id, title, description,
    status, property_type, repair_scope, location_lat, location_lng, address_label
) VALUES (
    'prj_1', 'org_1', 'cli_1', 'usr_1', 'Fasada domu Novak',
    'Znecistena severni stena a lokalni praskliny kolem oken.',
    'analysed', 'facade', 'local_repair', 50.087, 14.421, 'Praha 1'
);

INSERT OR IGNORE INTO project_photos (
    id, project_id, storage_key, original_filename, mime_type, file_size,
    width, height, taken_at, exif_lat, exif_lng, sort_order
) VALUES (
    'pho_1', 'prj_1', 'projects/prj_1/front-view.jpg', 'front-view.jpg', 'image/jpeg',
    2450000, 1600, 1200, CURRENT_TIMESTAMP, 50.087, 14.421, 1
);

INSERT OR IGNORE INTO analysis_jobs (
    id, project_id, status, job_type, requested_by_user_id, started_at, finished_at, error_message
) VALUES (
    'job_1', 'prj_1', 'completed', 'initial_review', 'usr_1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL
);

INSERT OR IGNORE INTO analysis_results (
    id, project_id, analysis_job_id, object_type, surface_condition,
    recommended_scope, estimated_area_sqm, area_confidence, mask_polygon_json,
    materials_suggestion_json, workflow_suggestion_json, model_name, model_version
) VALUES (
    'ana_1',
    'prj_1',
    'job_1',
    'facade',
    'damaged',
    'local_repair',
    42.5,
    0.72,
    '[{"x":0.1,"y":0.2},{"x":0.82,"y":0.18},{"x":0.86,"y":0.84},{"x":0.14,"y":0.88}]',
    '[{"name":"Penetrace","unit":"l","quantity":18},{"name":"Opravna smes","unit":"kg","quantity":120}]',
    '["Ocistit povrch","Lokalne opravit praskliny","Aplikovat finalni nater"]',
    'mock-vision',
    '0.1'
);

INSERT OR IGNORE INTO quote_variants (
    id, project_id, analysis_result_id, pricing_profile_id, variant_type,
    labor_cost, material_cost, other_cost, margin_pct, total_ex_vat,
    vat_amount, total_inc_vat, created_at, updated_at
) VALUES
(
    'qv_1', 'prj_1', 'ana_1', 'price_default', 'economy',
    16800, 13800, 4200, 12, 38976, 8184.96, 47160.96, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
),
(
    'qv_2', 'prj_1', 'ana_1', 'price_default', 'standard',
    19320, 18630, 4700, 18, 50248.60, 10552.21, 60800.81, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
),
(
    'qv_3', 'prj_1', 'ana_1', 'price_default', 'premium',
    21840, 24840, 5500, 28, 66890.20, 14046.94, 80937.14, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO quote_items (
    id, quote_variant_id, item_type, name, description, quantity, unit, unit_price, total_price, sort_order
) VALUES
(
    'qi_1', 'qv_1', 'labor', 'Cisteni a oprava fasady', 'Zakladni pracovni rozsah', 42.5, 'm2', 395.29, 16800, 1
),
(
    'qi_2', 'qv_2', 'labor', 'Standardni oprava fasady', 'Rozsireny pracovni rozsah', 42.5, 'm2', 454.59, 19320, 1
),
(
    'qi_3', 'qv_3', 'labor', 'Premium oprava fasady', 'Nejkvalitnejsi postup a kontrola detailu', 42.5, 'm2', 513.88, 21840, 1
);
"""


def main():
    DB_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.executescript(
            """
            DELETE FROM quote_items;
            DELETE FROM quote_variants;
            DELETE FROM analysis_results;
            DELETE FROM analysis_jobs;
            DELETE FROM project_photos;
            DELETE FROM projects;
            DELETE FROM pricing_profiles;
            DELETE FROM clients;
            DELETE FROM users;
            DELETE FROM organizations;
            """
        )
        connection.executescript(SEED_SQL)
        connection.commit()

        cursor = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()

    print(f"SQLite bootstrap completed: {DB_PATH}")
    print("Tables:")
    for table in tables:
        print(f"- {table}")


if __name__ == "__main__":
    main()
