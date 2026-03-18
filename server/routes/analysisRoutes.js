const express = require("express");
const { getProjectById: getProjectByIdFromDb } = require("../repositories/projectRepository");
const {
    getLatestAnalysisResult: getLatestAnalysisResultFromDb,
    createAnalysisRecord,
    updateLatestAnalysisManualSelection
} = require("../repositories/analysisRepository");
const { listPhotosByProjectId } = require("../repositories/photoRepository");
const { runProjectAnalysis, describeAnalysisProvider } = require("../ai/analysisService");
const {
    getProjectById,
    getLatestAnalysisResult
} = require("../data/mockStore");

const router = express.Router({ mergeParams: true });

router.get("/", (req, res) => {
    const project = getProjectByIdFromDb(req.params.projectId) || getProjectById(req.params.projectId);
    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    const result = getLatestAnalysisResultFromDb(req.params.projectId) || getLatestAnalysisResult(req.params.projectId);
    if (!result) {
        return res.status(404).json({ error: "No analysis result found." });
    }

    return res.json(result);
});

router.post("/", async (req, res) => {
    const project = getProjectByIdFromDb(req.params.projectId) || getProjectById(req.params.projectId);
    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    try {
        const photos = listPhotosByProjectId(project.id);
        const analysis = await runProjectAnalysis({ project, photos });
        const outcome = createAnalysisRecord(project, analysis);

        return res.status(202).json({
            jobId: outcome.job.id,
            status: outcome.job.status,
            provider: outcome.job.provider,
            modelName: outcome.result?.model_name,
            modelVersion: outcome.result?.model_version
        });
    } catch (error) {
        const providerInfo = (() => {
            try {
                return describeAnalysisProvider();
            } catch {
                return null;
            }
        })();

        if (["AI_PROVIDER_UNKNOWN", "AI_PROVIDER_NOT_CONFIGURED", "AI_PROVIDER_NOT_IMPLEMENTED"].includes(error.code)) {
            return res.status(503).json({
                error: error.message,
                provider: providerInfo?.providerKey || null
            });
        }

        throw error;
    }
});

router.patch("/", (req, res) => {
    const project = getProjectByIdFromDb(req.params.projectId) || getProjectById(req.params.projectId);
    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    const {
        referencePhotoId,
        selectedRepairPolygon,
        manualAreaSqm,
        finalAreaSource
    } = req.body || {};

    if (manualAreaSqm !== undefined && manualAreaSqm !== null) {
        const numericArea = Number(manualAreaSqm);
        if (!Number.isFinite(numericArea) || numericArea <= 0) {
            return res.status(400).json({ error: "manualAreaSqm must be a positive number." });
        }
    }

    if (finalAreaSource && !["ai", "manual"].includes(finalAreaSource)) {
        return res.status(400).json({ error: "finalAreaSource must be either 'ai' or 'manual'." });
    }

    if (selectedRepairPolygon !== undefined && selectedRepairPolygon !== null && !Array.isArray(selectedRepairPolygon)) {
        return res.status(400).json({ error: "selectedRepairPolygon must be an array of points." });
    }

    const updated = updateLatestAnalysisManualSelection(req.params.projectId, {
        referencePhotoId: referencePhotoId ?? undefined,
        selectedRepairPolygon: selectedRepairPolygon ?? undefined,
        manualAreaSqm: manualAreaSqm === undefined ? undefined : (manualAreaSqm === null ? null : Number(manualAreaSqm)),
        finalAreaSource: finalAreaSource ?? undefined
    });

    if (!updated) {
        return res.status(404).json({ error: "No analysis result found." });
    }

    return res.json(updated);
});

module.exports = router;
