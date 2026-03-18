const express = require("express");
const {
    listSuppliers,
    updateSupplier
} = require("../repositories/supplierRepository");

const router = express.Router();
const ALLOWED_INTEGRATION_TYPES = new Set(["manual", "csv_import", "api", "partner_feed"]);

router.get("/", (req, res, next) => {
    try {
        const items = listSuppliers({
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

router.patch("/:supplierId", (req, res, next) => {
    const {
        name,
        websiteUrl,
        integrationType,
        contactName,
        contactEmail
    } = req.body;

    if (typeof name !== "string" || name.trim().length === 0) {
        return res.status(400).json({ error: "name must be a non-empty string." });
    }

    if (!ALLOWED_INTEGRATION_TYPES.has(integrationType)) {
        return res.status(400).json({ error: "integrationType must be one of: manual, csv_import, api, partner_feed." });
    }

    if (websiteUrl !== null && websiteUrl !== undefined && typeof websiteUrl !== "string") {
        return res.status(400).json({ error: "websiteUrl must be a string or null." });
    }

    if (contactName !== null && contactName !== undefined && typeof contactName !== "string") {
        return res.status(400).json({ error: "contactName must be a string or null." });
    }

    if (contactEmail !== null && contactEmail !== undefined && typeof contactEmail !== "string") {
        return res.status(400).json({ error: "contactEmail must be a string or null." });
    }

    try {
        const updated = updateSupplier(req.params.supplierId, {
            name: name.trim(),
            website_url: websiteUrl ? websiteUrl.trim() : null,
            integration_type: integrationType,
            contact_name: contactName ? contactName.trim() : null,
            contact_email: contactEmail ? contactEmail.trim() : null
        });

        if (!updated) {
            return res.status(404).json({ error: "Supplier not found." });
        }

        return res.json(updated);
    } catch (error) {
        return next(error);
    }
});

module.exports = router;
