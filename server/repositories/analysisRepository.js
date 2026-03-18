const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const databasePath = path.resolve(__dirname, "../../prisma/dev.db");

function openDatabase() {
    const database = new DatabaseSync(databasePath);
    database.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL;");
    return database;
}

function parseJsonField(value) {
    if (!value) {
        return null;
    }

    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

function mapAnalysisResult(row) {
    if (!row) {
        return null;
    }

    return {
        id: row.id,
        project_id: row.project_id,
        analysis_job_id: row.analysis_job_id,
        reference_photo_id: row.reference_photo_id,
        object_type: row.object_type,
        surface_condition: row.surface_condition,
        recommended_scope: row.recommended_scope,
        estimated_area_sqm: row.estimated_area_sqm,
        area_confidence: row.area_confidence,
        selected_repair_polygon_json: parseJsonField(row.selected_repair_polygon_json),
        manual_area_sqm: row.manual_area_sqm,
        final_area_source: row.final_area_source,
        mask_polygon_json: parseJsonField(row.mask_polygon_json),
        materials_suggestion_json: parseJsonField(row.materials_suggestion_json),
        workflow_suggestion_json: parseJsonField(row.workflow_suggestion_json),
        model_name: row.model_name,
        model_version: row.model_version,
        created_at: row.created_at
    };
}

function getLatestAnalysisResult(projectId) {
    const database = openDatabase();

    try {
        const row = database.prepare(`
            SELECT *
            FROM analysis_results
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        `).get(projectId);

        return mapAnalysisResult(row);
    } finally {
        database.close();
    }
}

function createAnalysisRecord(project, analysis) {
    const database = openDatabase();

    try {
        const nextJobId = `job_${Date.now()}`;
        const nextAnalysisId = `ana_${Date.now()}`;
        const timestamp = new Date().toISOString();
        const jobStatus = analysis.jobStatus || "completed";
        const objectType = analysis.objectType || "facade";
        const recommendedScope = analysis.recommendedScope || "local_repair";
        const estimatedArea = Number(analysis.estimatedAreaSqm || 0);
        const mask = analysis.maskPolygon || [];
        const materials = analysis.materials || [];
        const workflow = analysis.workflow || [];

        database.prepare(`
            INSERT INTO analysis_jobs (
                id,
                project_id,
                status,
                job_type,
                requested_by_user_id,
                started_at,
                finished_at,
                error_message,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
            nextJobId,
            project.id,
            jobStatus,
            analysis.jobType || "manual_trigger",
            project.created_by_user_id || "usr_1",
            timestamp,
            timestamp,
            analysis.errorMessage || null,
            timestamp
        );

        database.prepare(`
            INSERT INTO analysis_results (
                id,
                project_id,
                analysis_job_id,
                reference_photo_id,
                object_type,
                surface_condition,
                recommended_scope,
                estimated_area_sqm,
                area_confidence,
                selected_repair_polygon_json,
                manual_area_sqm,
                final_area_source,
                mask_polygon_json,
                materials_suggestion_json,
                workflow_suggestion_json,
                model_name,
                model_version,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
            nextAnalysisId,
            project.id,
            nextJobId,
            analysis.referencePhotoId || null,
            objectType,
            analysis.surfaceCondition || "requires_attention",
            recommendedScope,
            estimatedArea,
            Number(analysis.areaConfidence || 0),
            analysis.selectedRepairPolygon ? JSON.stringify(analysis.selectedRepairPolygon) : null,
            analysis.manualAreaSqm ?? null,
            analysis.finalAreaSource || "ai",
            JSON.stringify(mask),
            JSON.stringify(materials),
            JSON.stringify(workflow),
            analysis.modelName || "mock-vision",
            analysis.modelVersion || "0.1",
            timestamp
        );

        database.prepare(`
            UPDATE projects
            SET status = ?, property_type = ?, repair_scope = ?, updated_at = ?
            WHERE id = ?
        `).run(
            "analysed",
            objectType,
            recommendedScope,
            timestamp,
            project.id
        );

        return {
            job: {
                id: nextJobId,
                status: jobStatus,
                provider: analysis.providerKey || "mock"
            },
            result: getLatestAnalysisResult(project.id)
        };
    } finally {
        database.close();
    }
}

function updateLatestAnalysisManualSelection(projectId, changes) {
    const database = openDatabase();

    try {
        const latest = database.prepare(`
            SELECT *
            FROM analysis_results
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        `).get(projectId);

        if (!latest) {
            return null;
        }

        const nextManualArea = Object.prototype.hasOwnProperty.call(changes, "manualAreaSqm")
            ? changes.manualAreaSqm
            : latest.manual_area_sqm;
        const nextReferencePhotoId = Object.prototype.hasOwnProperty.call(changes, "referencePhotoId")
            ? changes.referencePhotoId
            : latest.reference_photo_id;
        const nextPolygon = Object.prototype.hasOwnProperty.call(changes, "selectedRepairPolygon")
            ? changes.selectedRepairPolygon
            : parseJsonField(latest.selected_repair_polygon_json);
        let nextAreaSource = Object.prototype.hasOwnProperty.call(changes, "finalAreaSource")
            ? changes.finalAreaSource
            : latest.final_area_source;

        if (nextManualArea === null || nextManualArea === undefined) {
            nextAreaSource = "ai";
        } else if (!nextAreaSource) {
            nextAreaSource = "manual";
        }

        database.prepare(`
            UPDATE analysis_results
            SET reference_photo_id = ?,
                selected_repair_polygon_json = ?,
                manual_area_sqm = ?,
                final_area_source = ?
            WHERE id = ?
        `).run(
            nextReferencePhotoId || null,
            nextPolygon ? JSON.stringify(nextPolygon) : null,
            nextManualArea ?? null,
            nextAreaSource || "ai",
            latest.id
        );

        return getLatestAnalysisResult(projectId);
    } finally {
        database.close();
    }
}

module.exports = {
    getLatestAnalysisResult,
    createAnalysisRecord,
    updateLatestAnalysisManualSelection
};
