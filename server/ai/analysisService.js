"use strict";

const mockVisionProvider = require("./providers/mockVisionProvider");
const openaiVisionProvider = require("./providers/openaiVisionProvider");

const providers = {
    mock: mockVisionProvider,
    openai: openaiVisionProvider
};

function getConfiguredProviderKey() {
    return String(process.env.AI_ANALYSIS_PROVIDER || "mock").trim().toLowerCase();
}

function getAnalysisProvider() {
    const providerKey = getConfiguredProviderKey();
    const provider = providers[providerKey];

    if (!provider) {
        const error = new Error(`Unknown AI analysis provider: ${providerKey}`);
        error.code = "AI_PROVIDER_UNKNOWN";
        throw error;
    }

    return provider;
}

function normalizePhotoInputs(photos = []) {
    return photos.map(photo => ({
        id: photo.id,
        originalFilename: photo.originalFilename || null,
        mimeType: photo.mimeType || null,
        fileSize: typeof photo.fileSize === "number" ? photo.fileSize : null,
        width: typeof photo.width === "number" ? photo.width : null,
        height: typeof photo.height === "number" ? photo.height : null,
        orientation:
            typeof photo.width === "number" && typeof photo.height === "number"
                ? (photo.width >= photo.height ? "landscape" : "portrait")
                : "unknown",
        takenAt: photo.takenAt || null,
        hasGps: typeof photo.exifLat === "number" && typeof photo.exifLng === "number",
        location: {
            lat: typeof photo.exifLat === "number" ? photo.exifLat : null,
            lng: typeof photo.exifLng === "number" ? photo.exifLng : null
        },
        url: photo.url || null
    }));
}

async function runProjectAnalysis({ project, photos = [] }) {
    const provider = getAnalysisProvider();
    const normalizedPhotos = normalizePhotoInputs(photos);
    const result = await provider.analyzeProject({ project, photos: normalizedPhotos });

    return {
        providerKey: result.providerKey || provider.key,
        jobType: result.jobType || "manual_trigger",
        objectType: result.objectType,
        surfaceCondition: result.surfaceCondition,
        recommendedScope: result.recommendedScope,
        estimatedAreaSqm: result.estimatedAreaSqm,
        areaConfidence: result.areaConfidence,
        maskPolygon: result.maskPolygon,
        materials: result.materials,
        workflow: result.workflow,
        modelName: result.modelName || provider.key,
        modelVersion: result.modelVersion || "1.0"
    };
}

function describeAnalysisProvider() {
    const provider = getAnalysisProvider();

    return {
        providerKey: provider.key,
        mode: provider.key === "mock" ? "development" : "external"
    };
}

module.exports = {
    runProjectAnalysis,
    describeAnalysisProvider,
    normalizePhotoInputs
};
