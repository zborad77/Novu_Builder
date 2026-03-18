const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const databasePath = path.resolve(__dirname, "../../prisma/dev.db");

function openDatabase() {
    const database = new DatabaseSync(databasePath);
    database.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL;");
    return database;
}

function mapSupplierRow(row) {
    if (!row) {
        return null;
    }

    return {
        id: row.id,
        organization_id: row.organization_id,
        name: row.name,
        code: row.code,
        website_url: row.website_url,
        integration_type: row.integration_type,
        is_active: Boolean(row.is_active),
        contact_name: row.contact_name,
        contact_email: row.contact_email,
        created_at: row.created_at,
        updated_at: row.updated_at
    };
}

function listSuppliers({ organizationId = "org_1", activeOnly = true } = {}) {
    const database = openDatabase();

    try {
        const conditions = ["organization_id = ?"];
        const params = [organizationId];

        if (activeOnly) {
            conditions.push("is_active = 1");
        }

        const rows = database.prepare(`
            SELECT *
            FROM suppliers
            WHERE ${conditions.join(" AND ")}
            ORDER BY name ASC
        `).all(...params);

        return rows.map(mapSupplierRow);
    } finally {
        database.close();
    }
}

function getSupplierById(supplierId) {
    const database = openDatabase();

    try {
        const row = database.prepare(`
            SELECT *
            FROM suppliers
            WHERE id = ?
        `).get(supplierId);

        return mapSupplierRow(row);
    } finally {
        database.close();
    }
}

function updateSupplier(supplierId, changes) {
    const database = openDatabase();

    try {
        const existing = database.prepare(`
            SELECT *
            FROM suppliers
            WHERE id = ?
        `).get(supplierId);

        if (!existing) {
            return null;
        }

        const timestamp = new Date().toISOString();
        const nextValues = {
            name: Object.prototype.hasOwnProperty.call(changes, "name")
                ? changes.name
                : existing.name,
            website_url: Object.prototype.hasOwnProperty.call(changes, "website_url")
                ? changes.website_url
                : existing.website_url,
            integration_type: Object.prototype.hasOwnProperty.call(changes, "integration_type")
                ? changes.integration_type
                : existing.integration_type,
            contact_name: Object.prototype.hasOwnProperty.call(changes, "contact_name")
                ? changes.contact_name
                : existing.contact_name,
            contact_email: Object.prototype.hasOwnProperty.call(changes, "contact_email")
                ? changes.contact_email
                : existing.contact_email
        };

        database.prepare(`
            UPDATE suppliers
            SET
                name = ?,
                website_url = ?,
                integration_type = ?,
                contact_name = ?,
                contact_email = ?,
                updated_at = ?
            WHERE id = ?
        `).run(
            nextValues.name,
            nextValues.website_url,
            nextValues.integration_type,
            nextValues.contact_name,
            nextValues.contact_email,
            timestamp,
            supplierId
        );

        return getSupplierById(supplierId);
    } finally {
        database.close();
    }
}

module.exports = {
    listSuppliers,
    getSupplierById,
    updateSupplier
};
