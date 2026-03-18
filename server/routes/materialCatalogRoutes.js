const express = require("express");
const {
    listMaterialCatalog,
    listSupplierPricesByMaterialId,
    updateMaterialCatalogItem
} = require("../repositories/materialCatalogRepository");

const router = express.Router();

router.get("/", (req, res, next) => {
    try {
        const items = listMaterialCatalog({
            search: req.query.search,
            activeOnly: req.query.includeInactive === "true" ? false : true
        });

        return res.json({
            items,
            total: items.length
        });
    } catch (error) {
        return next(error);
    }
});

router.get("/:materialId/supplier-prices", (req, res, next) => {
    try {
        const items = listSupplierPricesByMaterialId(req.params.materialId);

        return res.json({
            items,
            total: items.length
        });
    } catch (error) {
        return next(error);
    }
});

router.patch("/:materialId", (req, res, next) => {
    const { defaultUnitPrice, defaultSupplierId, notes } = req.body;

    if (typeof defaultUnitPrice !== "number" || Number.isNaN(defaultUnitPrice) || defaultUnitPrice < 0) {
        return res.status(400).json({ error: "defaultUnitPrice must be a valid non-negative number." });
    }

    try {
        const updated = updateMaterialCatalogItem(req.params.materialId, {
            default_unit_price: defaultUnitPrice,
            default_supplier_id: defaultSupplierId || null,
            notes: typeof notes === "string" ? notes.trim() : null
        });

        if (!updated) {
            return res.status(404).json({ error: "Material not found." });
        }

        return res.json(updated);
    } catch (error) {
        return next(error);
    }
});

module.exports = router;
