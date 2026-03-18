const express = require("express");
const multer = require("multer");
const { getProjectById: getProjectByIdFromDb } = require("../repositories/projectRepository");
const {
    toResponse,
    listPhotosByProjectId,
    addPhotoRecord,
    removePhotoRecord,
    setPrimaryPhotoRecord
} = require("../repositories/photoRepository");
const { saveOriginalPhoto } = require("../storage/localPhotoStorage");
const {
    getProjectById,
} = require("../data/mockStore");

const router = express.Router({ mergeParams: true });
const upload = multer({
    storage: multer.memoryStorage(),
    limits: {
        fileSize: 20 * 1024 * 1024,
        files: 10
    }
});

router.get("/", (req, res) => {
    const { projectId } = req.params;
    const project = getProjectByIdFromDb(projectId) || getProjectById(projectId);

    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    const photos = listPhotosByProjectId(projectId);

    return res.json({
        items: photos,
        meta: {
            minimumRecommendedCount: 3,
            hasMinimumCount: photos.length >= 3,
            primaryPhotoId: photos.find(photo => photo.isPrimary)?.id || null,
            derivativeStrategy: {
                original: "archival-source",
                preview: "ui-optimized-max-edge-1600",
                aiInput: "analysis-optimized-max-edge-1280"
            }
        }
    });
});

router.post("/", upload.array("files", 10), (req, res) => {
    const { projectId } = req.params;
    const project = getProjectByIdFromDb(projectId) || getProjectById(projectId);

    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    const multipartFiles = Array.isArray(req.files) ? req.files : [];
    const jsonFiles = Array.isArray(req.body.files) ? req.body.files : [];

    if (multipartFiles.length === 0 && jsonFiles.length === 0) {
        return res.status(400).json({
            error: "This endpoint expects multipart/form-data files or a JSON body with a files array."
        });
    }

    const uploaded = jsonFiles.map((file, index) => {
        const filename = file.originalFilename || `photo-${Date.now()}-${index + 1}.jpg`;
        const photo = addPhotoRecord(projectId, {
            storage_key: `projects/${projectId}/${filename}`,
            original_filename: filename,
            mime_type: file.mimeType || "image/jpeg",
            file_size: file.fileSize || 0,
            width: file.width || null,
            height: file.height || null,
            taken_at: file.takenAt || null,
            exif_lat: file.exifLat || null,
            exif_lng: file.exifLng || null,
            is_primary: file.isPrimary || false,
            sort_order: file.sortOrder || undefined
        });

        return {
            id: photo.id,
            storageKey: photo.storage_key,
            isPrimary: photo.is_primary,
            processingStatus: photo.processing_status,
            variants: toResponse(photo).variants
        };
    });

    const multipartUploaded = multipartFiles.map((file, index) => {
        const stored = saveOriginalPhoto({
            projectId,
            originalFilename: file.originalname || `upload-${Date.now()}-${index + 1}.bin`,
            buffer: file.buffer
        });

        const photo = addPhotoRecord(projectId, {
            storage_key: stored.storageKey,
            original_filename: file.originalname || `upload-${Date.now()}-${index + 1}.bin`,
            mime_type: file.mimetype || "application/octet-stream",
            file_size: file.size || 0,
            processing_status: "original_uploaded",
            is_primary: req.body.isPrimary === "true" && index === 0
        });

        return {
            id: photo.id,
            storageKey: photo.storage_key,
            isPrimary: photo.is_primary,
            processingStatus: photo.processing_status,
            variants: toResponse(photo).variants
        };
    });

    return res.status(201).json({ uploaded: [...uploaded, ...multipartUploaded] });
});

router.patch("/:photoId/primary", (req, res) => {
    const { projectId, photoId } = req.params;
    const project = getProjectByIdFromDb(projectId) || getProjectById(projectId);

    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    const photo = setPrimaryPhotoRecord(projectId, photoId);
    if (!photo) {
        return res.status(404).json({ error: "Photo not found." });
    }

    return res.json({
        message: "Primary photo updated.",
        photo
    });
});

router.delete("/:photoId", (req, res) => {
    const { projectId, photoId } = req.params;
    const project = getProjectByIdFromDb(projectId) || getProjectById(projectId);

    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    const removed = removePhotoRecord(projectId, photoId);
    if (!removed) {
        return res.status(404).json({ error: "Photo not found." });
    }

    return res.json({ message: "Photo removed." });
});

module.exports = router;
