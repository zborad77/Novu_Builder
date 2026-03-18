const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const databasePath = path.resolve(__dirname, "../../prisma/dev.db");

function openDatabase() {
    const database = new DatabaseSync(databasePath);
    database.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL;");
    return database;
}

function mapMaterialRow(row) {
    if (!row) {
        return null;
    }

    return {
        id: row.id,
        organization_id: row.organization_id,
        name: row.name,
        category: row.category,
        unit: row.unit,
        norm_per_sqm: row.norm_per_sqm,
        default_unit_price: row.default_unit_price,
        default_supplier_id: row.default_supplier_id,
        default_supplier_name: row.default_supplier_name,
        is_active: Boolean(row.is_active),
        notes: row.notes,
        created_at: row.created_at,
        updated_at: row.updated_at
    };
}

function mapSupplierPriceRow(row) {
    if (!row) {
        return null;
    }

    return {
        id: row.id,
        material_catalog_id: row.material_catalog_id,
        supplier_id: row.supplier_id,
        supplier_name: row.supplier_name,
        supplier_product_name: row.supplier_product_name,
        supplier_sku: row.supplier_sku,
        unit: row.unit,
        unit_price: row.unit_price,
        currency: row.currency,
        availability_status: row.availability_status,
        source_type: row.source_type,
        source_url: row.source_url,
        valid_from: row.valid_from,
        valid_to: row.valid_to,
        last_seen_at: row.last_seen_at,
        created_at: row.created_at,
        updated_at: row.updated_at
    };
}

function listMaterialCatalog({ organizationId = "org_1", activeOnly = true, search = null } = {}) {
    const database = openDatabase();

    try {
        const conditions = ["mc.organization_id = ?"];
        const params = [organizationId];

        if (activeOnly) {
            conditions.push("mc.is_active = 1");
        }

        if (search) {
            conditions.push("(LOWER(mc.name) LIKE ? OR LOWER(COALESCE(mc.category, '')) LIKE ?)");
            const searchValue = `%${String(search).toLowerCase()}%`;
            params.push(searchValue, searchValue);
        }

        const rows = database.prepare(`
            SELECT
                mc.*,
                s.name AS default_supplier_name
            FROM material_catalog mc
            LEFT JOIN suppliers s ON s.id = mc.default_supplier_id
            WHERE ${conditions.join(" AND ")}
            ORDER BY mc.name ASC
        `).all(...params);

        return rows.map(mapMaterialRow);
    } finally {
        database.close();
    }
}

function listSupplierPricesByMaterialId(materialId) {
    const database = openDatabase();

    try {
        const rows = database.prepare(`
            SELECT
                smp.*,
                s.name AS supplier_name
            FROM supplier_material_prices smp
            INNER JOIN suppliers s ON s.id = smp.supplier_id
            WHERE smp.material_catalog_id = ?
            ORDER BY smp.unit_price ASC, s.name ASC
        `).all(materialId);

        return rows.map(mapSupplierPriceRow);
    } finally {
        database.close();
    }
}

function getMaterialById(materialId) {
    const database = openDatabase();

    try {
        const row = database.prepare(`
            SELECT
                mc.*,
                s.name AS default_supplier_name
            FROM material_catalog mc
            LEFT JOIN suppliers s ON s.id = mc.default_supplier_id
            WHERE mc.id = ?
        `).get(materialId);

        return mapMaterialRow(row);
    } finally {
        database.close();
    }
}

function updateMaterialCatalogItem(materialId, changes) {
    const database = openDatabase();

    try {
        const existing = database.prepare(`
            SELECT *
            FROM material_catalog
            WHERE id = ?
        `).get(materialId);

        if (!existing) {
            return null;
        }

        const timestamp = new Date().toISOString();
        const nextValues = {
            default_unit_price: Object.prototype.hasOwnProperty.call(changes, "default_unit_price")
                ? changes.default_unit_price
                : existing.default_unit_price,
            default_supplier_id: Object.prototype.hasOwnProperty.call(changes, "default_supplier_id")
                ? (changes.default_supplier_id ?? null)
                : existing.default_supplier_id,
            notes: Object.prototype.hasOwnProperty.call(changes, "notes")
                ? changes.notes
                : existing.notes
        };

        database.prepare(`
            UPDATE material_catalog
            SET
                default_unit_price = ?,
                default_supplier_id = ?,
                notes = ?,
                updated_at = ?
            WHERE id = ?
        `).run(
            nextValues.default_unit_price,
            nextValues.default_supplier_id,
            nextValues.notes,
            timestamp,
            materialId
        );

        return getMaterialById(materialId);
    } finally {
        database.close();
    }
}

module.exports = {
    listMaterialCatalog,
    listSupplierPricesByMaterialId,
    getMaterialById,
    updateMaterialCatalogItem
};
