const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const databasePath = path.resolve(__dirname, "../../prisma/dev.db");

function openDatabase() {
    const database = new DatabaseSync(databasePath);
    database.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL;");
    return database;
}

function mapProjectRow(row) {
    if (!row) {
        return null;
    }

    return {
        id: row.id,
        organization_id: row.organization_id,
        client_id: row.client_id,
        created_by_user_id: row.created_by_user_id,
        title: row.title,
        description: row.description,
        status: row.status,
        property_type: row.property_type,
        repair_scope: row.repair_scope,
        location_lat: row.location_lat,
        location_lng: row.location_lng,
        address_label: row.address_label,
        created_at: row.created_at,
        updated_at: row.updated_at
    };
}

function toSummary(project) {
    return {
        id: project.id,
        title: project.title,
        status: project.status,
        propertyType: project.property_type,
        repairScope: project.repair_scope,
        addressLabel: project.address_label,
        photoCount: 0,
        estimatedAreaSqm: null,
        latestQuoteTotal: null,
        updatedAt: project.updated_at
    };
}

function toDetail(project, client) {
    return {
        id: project.id,
        title: project.title,
        description: project.description,
        status: project.status,
        propertyType: project.property_type,
        repairScope: project.repair_scope,
        location: {
            lat: project.location_lat,
            lng: project.location_lng,
            addressLabel: project.address_label
        },
        client: client ? {
            id: client.id,
            fullName: client.full_name,
            companyName: client.company_name,
            email: client.email,
            phone: client.phone
        } : null,
        photos: [],
        latestAnalysis: null,
        quoteVariants: [],
        createdAt: project.created_at,
        updatedAt: project.updated_at
    };
}

function listProjects({ status, search }) {
    const database = openDatabase();

    try {
        const conditions = [];
        const params = [];

        if (status) {
            conditions.push("status = ?");
            params.push(status);
        }

        if (search) {
            conditions.push("(LOWER(title) LIKE ? OR LOWER(COALESCE(description, '')) LIKE ?)");
            const searchValue = `%${String(search).toLowerCase()}%`;
            params.push(searchValue, searchValue);
        }

        const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
        const statement = database.prepare(`
            SELECT *
            FROM projects
            ${whereClause}
            ORDER BY updated_at DESC, created_at DESC
        `);
        const rows = statement.all(...params);

        return rows.map(row => toSummary(mapProjectRow(row)));
    } finally {
        database.close();
    }
}

function createProjectRecord(input) {
    const database = openDatabase();

    try {
        const existing = database.prepare("SELECT COUNT(*) AS count FROM projects").get();
        const nextNumber = (existing?.count || 0) + 1;
        const projectId = `prj_${nextNumber}`;
        const timestamp = new Date().toISOString();

        database.prepare(`
            INSERT INTO projects (
                id,
                organization_id,
                client_id,
                created_by_user_id,
                title,
                description,
                status,
                property_type,
                repair_scope,
                location_lat,
                location_lng,
                address_label,
                created_at,
                updated_at
            ) VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
        `).run(
            projectId,
            input.organization_id || "org_1",
            input.client_id || null,
            input.created_by_user_id || "usr_1",
            input.title,
            input.description || "",
            "draft",
            input.property_type || null,
            input.repair_scope || null,
            input.location_lat || null,
            input.location_lng || null,
            input.address_label || null,
            timestamp,
            timestamp
        );

        const row = database.prepare("SELECT * FROM projects WHERE id = ?").get(projectId);
        return mapProjectRow(row);
    } finally {
        database.close();
    }
}

function getProjectById(projectId) {
    const database = openDatabase();

    try {
        const row = database.prepare("SELECT * FROM projects WHERE id = ?").get(projectId);
        return mapProjectRow(row);
    } finally {
        database.close();
    }
}

function getProjectDetail(projectId) {
    const database = openDatabase();

    try {
        const projectRow = database.prepare("SELECT * FROM projects WHERE id = ?").get(projectId);
        const project = mapProjectRow(projectRow);
        if (!project) {
            return null;
        }

        const client = project.client_id
            ? database.prepare("SELECT * FROM clients WHERE id = ?").get(project.client_id)
            : null;

        return toDetail(project, client);
    } finally {
        database.close();
    }
}

function updateProjectRecord(projectId, changes) {
    const database = openDatabase();

    try {
        const existingProject = database.prepare("SELECT * FROM projects WHERE id = ?").get(projectId);
        if (!existingProject) {
            return null;
        }

        const mappedProject = mapProjectRow(existingProject);
        const nextProject = {
            ...mappedProject,
            title: Object.prototype.hasOwnProperty.call(changes, "title") ? changes.title : mappedProject.title,
            description: Object.prototype.hasOwnProperty.call(changes, "description") ? changes.description : mappedProject.description,
            status: Object.prototype.hasOwnProperty.call(changes, "status") ? changes.status : mappedProject.status,
            property_type: Object.prototype.hasOwnProperty.call(changes, "property_type") ? changes.property_type : mappedProject.property_type,
            repair_scope: Object.prototype.hasOwnProperty.call(changes, "repair_scope") ? changes.repair_scope : mappedProject.repair_scope,
            location_lat: Object.prototype.hasOwnProperty.call(changes, "location_lat") ? changes.location_lat : mappedProject.location_lat,
            location_lng: Object.prototype.hasOwnProperty.call(changes, "location_lng") ? changes.location_lng : mappedProject.location_lng,
            address_label: Object.prototype.hasOwnProperty.call(changes, "address_label") ? changes.address_label : mappedProject.address_label,
            client_id: Object.prototype.hasOwnProperty.call(changes, "client_id")
                ? (changes.client_id ?? null)
                : (mappedProject.client_id ?? null),
            updated_at: new Date().toISOString()
        };

        database.prepare(`
            UPDATE projects
            SET
                title = ?,
                description = ?,
                status = ?,
                property_type = ?,
                repair_scope = ?,
                location_lat = ?,
                location_lng = ?,
                address_label = ?,
                client_id = ?,
                updated_at = ?
            WHERE id = ?
        `).run(
            nextProject.title,
            nextProject.description,
            nextProject.status,
            nextProject.property_type,
            nextProject.repair_scope,
            nextProject.location_lat,
            nextProject.location_lng,
            nextProject.address_label,
            nextProject.client_id,
            nextProject.updated_at,
            projectId
        );

        return getProjectDetail(projectId);
    } finally {
        database.close();
    }
}

module.exports = {
    listProjects,
    createProjectRecord,
    getProjectById,
    getProjectDetail,
    updateProjectRecord
};
