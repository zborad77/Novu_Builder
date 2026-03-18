const express = require("express");
const { getProjectById: getProjectByIdFromDb } = require("../repositories/projectRepository");
const {
    getAnalysisJobById: getAnalysisJobByIdFromDb,
    listQuoteVariantsByProjectId,
    recalculateQuoteVariants: recalculateQuoteVariantsInDb,
    updateQuoteVariantRecord
} = require("../repositories/quoteVariantRepository");
const {
    getProjectById,
    getQuoteVariantsByProjectId,
    getQuoteItemsByVariantId,
    recalculateQuoteVariants,
    updateQuoteVariant,
    getAnalysisJobById
} = require("../data/mockStore");

const router = express.Router();

router.get("/analysis-jobs/:jobId", (req, res) => {
    const job = getAnalysisJobByIdFromDb(req.params.jobId) || getAnalysisJobById(req.params.jobId);
    if (!job) {
        return res.status(404).json({ error: "Analysis job not found." });
    }

    return res.json(job);
});

router.get("/projects/:projectId/quote-variants", (req, res) => {
    const project = getProjectByIdFromDb(req.params.projectId) || getProjectById(req.params.projectId);
    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    const dbVariants = listQuoteVariantsByProjectId(req.params.projectId);
    const variants = dbVariants.length > 0
        ? dbVariants
        : getQuoteVariantsByProjectId(req.params.projectId).map(variant => ({
            ...variant,
            items: getQuoteItemsByVariantId(variant.id)
        }));

    return res.json({ items: variants });
});

router.post("/projects/:projectId/quote-variants/recalculate", (req, res) => {
    const project = getProjectByIdFromDb(req.params.projectId) || getProjectById(req.params.projectId);
    if (!project) {
        return res.status(404).json({ error: "Project not found." });
    }

    const variants = recalculateQuoteVariantsInDb(req.params.projectId) || recalculateQuoteVariants(req.params.projectId);
    if (!variants) {
        return res.status(400).json({
            error: "Quote variants cannot be recalculated without an analysis result."
        });
    }

    return res.json({
        variants: variants.map(variant => ({
            id: variant.id,
            variantType: variant.variant_type,
            totalIncVat: variant.total_inc_vat
        }))
    });
});

router.patch("/quote-variants/:variantId", (req, res) => {
    const updated = updateQuoteVariantRecord(req.params.variantId, {
        labor_cost: req.body.laborCost,
        material_cost: req.body.materialCost,
        other_cost: req.body.otherCost,
        margin_pct: req.body.marginPct
    }) || updateQuoteVariant(req.params.variantId, {
        labor_cost: req.body.laborCost,
        material_cost: req.body.materialCost,
        other_cost: req.body.otherCost,
        margin_pct: req.body.marginPct
    });

    if (!updated) {
        return res.status(404).json({ error: "Quote variant not found." });
    }

    return res.json(updated);
});

module.exports = router;
