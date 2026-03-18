const path = require('node:path')
const { DatabaseSync } = require('node:sqlite')

const PROJECT_ROOT = path.resolve(__dirname, '..')
const DB_PATH = path.join(PROJECT_ROOT, 'prisma', 'dev.db')

const DROP_SQL = `
DROP TABLE IF EXISTS quote_items;
DROP TABLE IF EXISTS quote_variants;
DROP TABLE IF EXISTS supplier_material_prices;
DROP TABLE IF EXISTS analysis_results;
DROP TABLE IF EXISTS analysis_jobs;
DROP TABLE IF EXISTS project_photos;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS material_catalog;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS pricing_profiles;
DROP TABLE IF EXISTS clients;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS organizations;
`

const SCHEMA_SQL = `
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
    labor_hours_per_sqm REAL NOT NULL DEFAULT 0.3,
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

CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    name TEXT NOT NULL,
    code TEXT,
    website_url TEXT,
    integration_type TEXT NOT NULL DEFAULT 'manual',
    is_active INTEGER NOT NULL DEFAULT 1,
    contact_name TEXT,
    contact_email TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS material_catalog (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    unit TEXT NOT NULL,
    norm_per_sqm REAL NOT NULL,
    default_unit_price REAL NOT NULL,
    default_supplier_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (default_supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS supplier_material_prices (
    id TEXT PRIMARY KEY,
    material_catalog_id TEXT NOT NULL,
    supplier_id TEXT NOT NULL,
    supplier_product_name TEXT,
    supplier_sku TEXT,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CZK',
    availability_status TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_url TEXT,
    valid_from TEXT,
    valid_to TEXT,
    last_seen_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (material_catalog_id) REFERENCES material_catalog(id) ON DELETE CASCADE,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
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
    preview_storage_key TEXT,
    ai_input_storage_key TEXT,
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    width INTEGER,
    height INTEGER,
    preview_file_size INTEGER,
    preview_width INTEGER,
    preview_height INTEGER,
    ai_input_file_size INTEGER,
    ai_input_width INTEGER,
    ai_input_height INTEGER,
    processing_status TEXT NOT NULL DEFAULT 'ready',
    taken_at TEXT,
    exif_lat REAL,
    exif_lng REAL,
    is_primary INTEGER NOT NULL DEFAULT 0,
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
    reference_photo_id TEXT,
    object_type TEXT,
    surface_condition TEXT,
    recommended_scope TEXT,
    estimated_area_sqm REAL,
    area_confidence REAL,
    selected_repair_polygon_json TEXT,
    manual_area_sqm REAL,
    final_area_source TEXT NOT NULL DEFAULT 'ai',
    mask_polygon_json TEXT,
    materials_suggestion_json TEXT,
    workflow_suggestion_json TEXT,
    model_name TEXT,
    model_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (analysis_job_id) REFERENCES analysis_jobs(id) ON DELETE SET NULL,
    FOREIGN KEY (reference_photo_id) REFERENCES project_photos(id) ON DELETE SET NULL
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
    material_catalog_id TEXT,
    supplier_id TEXT,
    price_source TEXT NOT NULL DEFAULT 'company_catalog',
    is_manual_override INTEGER NOT NULL DEFAULT 0,
    ai_suggested_unit_price REAL,
    supplier_reference_unit_price REAL,
    company_default_unit_price REAL,
    sort_order INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (quote_variant_id) REFERENCES quote_variants(id) ON DELETE CASCADE,
    FOREIGN KEY (material_catalog_id) REFERENCES material_catalog(id) ON DELETE SET NULL,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_organization_id ON projects(organization_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_suppliers_organization_id ON suppliers(organization_id);
CREATE INDEX IF NOT EXISTS idx_material_catalog_organization_id ON material_catalog(organization_id);
CREATE INDEX IF NOT EXISTS idx_supplier_material_prices_material_id ON supplier_material_prices(material_catalog_id);
CREATE INDEX IF NOT EXISTS idx_supplier_material_prices_supplier_id ON supplier_material_prices(supplier_id);
CREATE INDEX IF NOT EXISTS idx_project_photos_project_id ON project_photos(project_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_project_id ON analysis_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_analysis_results_project_id ON analysis_results(project_id);
CREATE INDEX IF NOT EXISTS idx_quote_variants_project_id ON quote_variants(project_id);
CREATE INDEX IF NOT EXISTS idx_quote_items_quote_variant_id ON quote_items(quote_variant_id);
`

const RESET_SQL = `
DELETE FROM quote_items;
DELETE FROM quote_variants;
DELETE FROM supplier_material_prices;
DELETE FROM analysis_results;
DELETE FROM analysis_jobs;
DELETE FROM project_photos;
DELETE FROM projects;
DELETE FROM material_catalog;
DELETE FROM suppliers;
DELETE FROM pricing_profiles;
DELETE FROM clients;
DELETE FROM users;
DELETE FROM organizations;
`

const SEED_SQL = `
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
    id, organization_id, name, hourly_rate, daily_rate, labor_hours_per_sqm, margin_economy_pct,
    margin_standard_pct, margin_premium_pct, vat_pct, currency, is_default
) VALUES (
    'price_default', 'org_1', 'Default profile', 520, 4200, 0.3, 12, 18, 28, 21, 'CZK', 1
);

INSERT OR IGNORE INTO suppliers (
    id, organization_id, name, code, website_url, integration_type, is_active, contact_name, contact_email
) VALUES
(
    'sup_dek', 'org_1', 'DEK', 'dek', 'https://www.dek.cz', 'manual', 1, '', ''
),
(
    'sup_stavmat', 'org_1', 'Stavmat', 'stavmat', 'https://www.stavmat.cz', 'manual', 1, '', ''
),
(
    'sup_invest', 'org_1', 'Invest', 'invest', '', 'manual', 1, '', ''
);

INSERT OR IGNORE INTO material_catalog (
    id, organization_id, name, category, unit, norm_per_sqm, default_unit_price, default_supplier_id, is_active, notes
) VALUES
(
    'mat_penetrace', 'org_1', 'Penetrace', 'coating', 'l', 0.35, 82, 'sup_dek', 1, 'Zakladni priprava podkladu'
),
(
    'mat_opravna_smes', 'org_1', 'Opravna smes', 'repair', 'kg', 2.8, 24, 'sup_stavmat', 1, 'Lokani opravy prasklin a odstreku'
),
(
    'mat_fasadni_nater', 'org_1', 'Fasadni nater', 'coating', 'kg', 0.45, 118, 'sup_dek', 1, 'Finalni vrstva pro standardni realizaci'
);

INSERT OR IGNORE INTO supplier_material_prices (
    id, material_catalog_id, supplier_id, supplier_product_name, supplier_sku, unit, unit_price,
    currency, availability_status, source_type, source_url, valid_from, valid_to, last_seen_at
) VALUES
(
    'smp_1', 'mat_penetrace', 'sup_dek', 'Penetrace DEK', 'DEK-PEN-01', 'l', 79,
    'CZK', 'in_stock', 'manual', 'https://www.dek.cz', CURRENT_TIMESTAMP, NULL, CURRENT_TIMESTAMP
),
(
    'smp_2', 'mat_penetrace', 'sup_stavmat', 'Penetrace Stavmat', 'STM-PEN-77', 'l', 84,
    'CZK', 'in_stock', 'manual', 'https://www.stavmat.cz', CURRENT_TIMESTAMP, NULL, CURRENT_TIMESTAMP
),
(
    'smp_3', 'mat_opravna_smes', 'sup_invest', 'Opravna smes Invest', 'INV-REP-12', 'kg', 23,
    'CZK', 'limited', 'manual', NULL, CURRENT_TIMESTAMP, NULL, CURRENT_TIMESTAMP
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
    id, project_id, storage_key, preview_storage_key, ai_input_storage_key, original_filename, mime_type, file_size,
    width, height, preview_file_size, preview_width, preview_height, ai_input_file_size, ai_input_width, ai_input_height,
    processing_status, taken_at, exif_lat, exif_lng, is_primary, sort_order
) VALUES
(
    'pho_1', 'prj_1', 'projects/prj_1/front-view.jpg', 'projects/prj_1/preview/front-view.jpg', 'projects/prj_1/ai/front-view.jpg', 'front-view.jpg', 'image/jpeg',
    2450000, 1600, 1200, 440000, 1600, 1200, 210000, 1280, 960, 'ready', CURRENT_TIMESTAMP, 50.087, 14.421, 1, 1
),
(
    'pho_2', 'prj_1', 'projects/prj_1/wide-angle.jpg', 'projects/prj_1/preview/wide-angle.jpg', 'projects/prj_1/ai/wide-angle.jpg', 'wide-angle.jpg', 'image/jpeg',
    2680000, 1800, 1200, 500000, 1600, 1067, 240000, 1280, 853, 'ready', CURRENT_TIMESTAMP, 50.087, 14.421, 0, 2
),
(
    'pho_3', 'prj_1', 'projects/prj_1/detail-window.jpg', 'projects/prj_1/preview/detail-window.jpg', 'projects/prj_1/ai/detail-window.jpg', 'detail-window.jpg', 'image/jpeg',
    1980000, 900, 1400, 360000, 900, 1400, 190000, 823, 1280, 'ready', CURRENT_TIMESTAMP, 50.087, 14.421, 0, 3
);

INSERT OR IGNORE INTO analysis_jobs (
    id, project_id, status, job_type, requested_by_user_id, started_at, finished_at, error_message
) VALUES (
    'job_1', 'prj_1', 'completed', 'initial_review', 'usr_1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL
);

INSERT OR IGNORE INTO analysis_results (
    id, project_id, analysis_job_id, reference_photo_id, object_type, surface_condition,
    recommended_scope, estimated_area_sqm, area_confidence, selected_repair_polygon_json, manual_area_sqm, final_area_source, mask_polygon_json,
    materials_suggestion_json, workflow_suggestion_json, model_name, model_version
) VALUES (
    'ana_1',
    'prj_1',
    'job_1',
    'pho_1',
    'facade',
    'damaged',
    'local_repair',
    42.5,
    0.72,
    NULL,
    NULL,
    'ai',
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
    id, quote_variant_id, item_type, name, description, quantity, unit, unit_price, total_price,
    material_catalog_id, supplier_id, price_source, is_manual_override, ai_suggested_unit_price,
    supplier_reference_unit_price, company_default_unit_price, sort_order, created_at, updated_at
) VALUES
(
    'qi_1', 'qv_1', 'labor', 'Cisteni a oprava fasady', 'Zakladni pracovni rozsah', 42.5, 'm2', 395.29, 16800,
    NULL, NULL, 'company_catalog', 0, 395.29, NULL, 395.29, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
),
(
    'qi_2', 'qv_2', 'material', 'Penetrace', 'AI navrzeny material pro pripravu podkladu', 18, 'l', 82, 1476,
    'mat_penetrace', 'sup_dek', 'company_catalog', 0, 80, 79, 82, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
),
(
    'qi_3', 'qv_3', 'material', 'Opravna smes', 'Rucne upravena cena materialu pro premium variantu', 120, 'kg', 26, 3120,
    'mat_opravna_smes', 'sup_invest', 'manual_override', 1, 24, 23, 24, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
);
`

function bootstrapDatabase() {
  const database = new DatabaseSync(DB_PATH)

  try {
    database.exec(DROP_SQL)
    database.exec(SCHEMA_SQL)
    database.exec(RESET_SQL)
    database.exec(SEED_SQL)

    const tables = database
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
      .all()
      .map(row => row.name)

    return { dbPath: DB_PATH, tables }
  } finally {
    database.close()
  }
}

if (require.main === module) {
  const { dbPath, tables } = bootstrapDatabase()
  console.log(`SQLite bootstrap completed: ${dbPath}`)
  console.log('Tables:')
  tables.forEach(table => {
    console.log(`- ${table}`)
  })
}

module.exports = { bootstrapDatabase, DB_PATH }
