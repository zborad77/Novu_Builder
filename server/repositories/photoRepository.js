const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const databasePath = path.resolve(__dirname, "../../prisma/dev.db");

function openDatabase() {
    const database = new DatabaseSync(databasePath);
    database.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL;");
    return database;
}

function mapPhotoRow(row) {
    if (!row) {
        return null;
    }

    return {
        id: row.id,
        project_id: row.project_id,
        storage_key: row.storage_key,
        preview_storage_key: row.preview_storage_key,
        ai_input_storage_key: row.ai_input_storage_key,
        original_filename: row.original_filename,
        mime_type: row.mime_type,
        file_size: row.file_size,
        width: row.width,
        height: row.height,
        preview_file_size: row.preview_file_size,
        preview_width: row.preview_width,
        preview_height: row.preview_height,
        ai_input_file_size: row.ai_input_file_size,
        ai_input_width: row.ai_input_width,
        ai_input_height: row.ai_input_height,
        processing_status: row.processing_status,
        taken_at: row.taken_at,
        exif_lat: row.exif_lat,
        exif_lng: row.exif_lng,
        is_primary: Boolean(row.is_primary),
        sort_order: row.sort_order,
        created_at: row.created_at
    };
}

function toResponse(photo) {
    return {
        id: photo.id,
        originalFilename: photo.original_filename,
        storageKey: photo.storage_key,
        mimeType: photo.mime_type,
        fileSize: photo.file_size,
        width: photo.width,
        height: photo.height,
        takenAt: photo.taken_at,
        exifLat: photo.exif_lat,
        exifLng: photo.exif_lng,
        processingStatus: photo.processing_status,
        isPrimary: photo.is_primary,
        sortOrder: photo.sort_order,
        url: `/mock-storage/${photo.storage_key}`,
        variants: {
            original: {
                storageKey: photo.storage_key,
                fileSize: photo.file_size,
                width: photo.width,
                height: photo.height,
                url: `/mock-storage/${photo.storage_key}`
            },
            preview: {
                storageKey: photo.preview_storage_key,
                fileSize: photo.preview_file_size,
                width: photo.preview_width,
                height: photo.preview_height,
                url: photo.preview_storage_key ? `/mock-storage/${photo.preview_storage_key}` : null
            },
            aiInput: {
                storageKey: photo.ai_input_storage_key,
                fileSize: photo.ai_input_file_size,
                width: photo.ai_input_width,
                height: photo.ai_input_height,
                url: photo.ai_input_storage_key ? `/mock-storage/${photo.ai_input_storage_key}` : null
            }
        }
    };
}

function getScaledDimensions(width, height, maxEdge) {
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
        return { width: null, height: null };
    }

    const currentMaxEdge = Math.max(width, height);
    if (currentMaxEdge <= maxEdge) {
        return { width, height };
    }

    const scale = maxEdge / currentMaxEdge;
    return {
        width: Math.max(1, Math.round(width * scale)),
        height: Math.max(1, Math.round(height * scale))
    };
}

function estimateDerivedFileSize(originalSize, derivedWidth, derivedHeight, originalWidth, originalHeight, compressionRatio) {
    if (!Number.isFinite(originalSize) || originalSize <= 0) {
        return null;
    }

    if (!Number.isFinite(derivedWidth) || !Number.isFinite(derivedHeight) || !Number.isFinite(originalWidth) || !Number.isFinite(originalHeight)) {
        return null;
    }

    const areaRatio = (derivedWidth * derivedHeight) / (originalWidth * originalHeight);
    return Math.max(20_000, Math.round(originalSize * areaRatio * compressionRatio));
}

function buildDerivedVariants(projectId, filename, input) {
    const originalWidth = input.width || null;
    const originalHeight = input.height || null;
    const originalSize = input.file_size || 0;
    const previewDimensions = getScaledDimensions(originalWidth, originalHeight, 1600);
    const aiInputDimensions = getScaledDimensions(originalWidth, originalHeight, 1280);

    return {
        preview_storage_key: input.preview_storage_key || `projects/${projectId}/preview/${filename}`,
        preview_width: input.preview_width || previewDimensions.width,
        preview_height: input.preview_height || previewDimensions.height,
        preview_file_size: input.preview_file_size || estimateDerivedFileSize(
            originalSize,
            previewDimensions.width,
            previewDimensions.height,
            originalWidth,
            originalHeight,
            0.72
        ),
        ai_input_storage_key: input.ai_input_storage_key || `projects/${projectId}/ai/${filename}`,
        ai_input_width: input.ai_input_width || aiInputDimensions.width,
        ai_input_height: input.ai_input_height || aiInputDimensions.height,
        ai_input_file_size: input.ai_input_file_size || estimateDerivedFileSize(
            originalSize,
            aiInputDimensions.width,
            aiInputDimensions.height,
            originalWidth,
            originalHeight,
            0.56
        )
    };
}

function listPhotosByProjectId(projectId) {
    const database = openDatabase();

    try {
        const rows = database.prepare(`
            SELECT *
            FROM project_photos
            WHERE project_id = ?
            ORDER BY sort_order ASC, created_at ASC
        `).all(projectId);

        return rows.map(row => toResponse(mapPhotoRow(row)));
    } finally {
        database.close();
    }
}

function addPhotoRecord(projectId, input) {
    const database = openDatabase();

    try {
        const existing = database.prepare("SELECT COUNT(*) AS count FROM project_photos").get();
        const nextNumber = (existing?.count || 0) + 1;
        const photoId = `pho_${nextNumber}`;
        const filename = input.original_filename || `photo-${Date.now()}.jpg`;
        const timestamp = new Date().toISOString();
        const shouldBePrimary = Boolean(input.is_primary) || getPhotoCount(database, projectId) === 0;
        const derivedVariants = buildDerivedVariants(projectId, filename, input);

        database.exec("BEGIN IMMEDIATE");

        if (shouldBePrimary) {
            database.prepare(`
                UPDATE project_photos
                SET is_primary = 0
                WHERE project_id = ?
            `).run(projectId);
        }

        database.prepare(`
            INSERT INTO project_photos (
                id,
                project_id,
                storage_key,
                preview_storage_key,
                ai_input_storage_key,
                original_filename,
                mime_type,
                file_size,
                width,
                height,
                preview_file_size,
                preview_width,
                preview_height,
                ai_input_file_size,
                ai_input_width,
                ai_input_height,
                processing_status,
                taken_at,
                exif_lat,
                exif_lng,
                is_primary,
                sort_order,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
            photoId,
            projectId,
            input.storage_key || `projects/${projectId}/${filename}`,
            derivedVariants.preview_storage_key,
            derivedVariants.ai_input_storage_key,
            filename,
            input.mime_type || "image/jpeg",
            input.file_size || 0,
            input.width || null,
            input.height || null,
            derivedVariants.preview_file_size,
            derivedVariants.preview_width,
            derivedVariants.preview_height,
            derivedVariants.ai_input_file_size,
            derivedVariants.ai_input_width,
            derivedVariants.ai_input_height,
            input.processing_status || "ready",
            input.taken_at || null,
            input.exif_lat || null,
            input.exif_lng || null,
            shouldBePrimary ? 1 : 0,
            input.sort_order || getNextSortOrder(database, projectId),
            timestamp
        );

        database.exec("COMMIT");
        const row = database.prepare("SELECT * FROM project_photos WHERE id = ?").get(photoId);
        return mapPhotoRow(row);
    } catch (error) {
        try {
            database.exec("ROLLBACK");
        } catch {
            // no-op
        }
        throw error;
    } finally {
        database.close();
    }
}

function getPhotoCount(database, projectId) {
    const row = database.prepare(`
        SELECT COUNT(*) AS photo_count
        FROM project_photos
        WHERE project_id = ?
    `).get(projectId);

    return row?.photo_count || 0;
}

function getNextSortOrder(database, projectId) {
    const row = database.prepare(`
        SELECT COALESCE(MAX(sort_order), 0) AS max_sort_order
        FROM project_photos
        WHERE project_id = ?
    `).get(projectId);

    return (row?.max_sort_order || 0) + 1;
}

function removePhotoRecord(projectId, photoId) {
    const database = openDatabase();

    try {
        const result = database.prepare(`
            DELETE FROM project_photos
            WHERE id = ? AND project_id = ?
        `).run(photoId, projectId);

        return result.changes > 0;
    } finally {
        database.close();
    }
}

function setPrimaryPhotoRecord(projectId, photoId) {
    const database = openDatabase();

    try {
        const target = database.prepare(`
            SELECT *
            FROM project_photos
            WHERE id = ? AND project_id = ?
        `).get(photoId, projectId);

        if (!target) {
            return null;
        }

        database.exec("BEGIN IMMEDIATE");
        database.prepare(`
            UPDATE project_photos
            SET is_primary = 0
            WHERE project_id = ?
        `).run(projectId);

        database.prepare(`
            UPDATE project_photos
            SET is_primary = 1
            WHERE id = ? AND project_id = ?
        `).run(photoId, projectId);
        database.exec("COMMIT");

        const updated = database.prepare(`
            SELECT *
            FROM project_photos
            WHERE id = ? AND project_id = ?
        `).get(photoId, projectId);

        return toResponse(mapPhotoRow(updated));
    } catch (error) {
        try {
            database.exec("ROLLBACK");
        } catch {
            // no-op
        }
        throw error;
    } finally {
        database.close();
    }
}

module.exports = {
    toResponse,
    listPhotosByProjectId,
    addPhotoRecord,
    removePhotoRecord,
    setPrimaryPhotoRecord
};
