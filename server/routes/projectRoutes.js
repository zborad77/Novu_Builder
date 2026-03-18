const express = require("express");
const {
    listProjects,
    createProjectRecord,
    getProjectById: getProjectByIdFromDb,
    getProjectDetail,
    updateProjectRecord
} = require("../repositories/projectRepository");
const {
    buildProjectDetail,
    getProjectById
} = require("../data/mockStore");

const router = express.Router();

router.get("/", (req, res, next) => {
    try {
        const items = listProjects({
            status: req.query.status,
            search: req.query.search
        });

        return res.json({
            items,
            total: items.length
        });
    } catch (error) {
        return next(error);
    }
});

router.post("/", (req, res, next) => {
    const {
        title,
        description,
        clientId,
        locationLat,
        locationLng,
        addressLabel
    } = req.body;

    if (!title || !String(title).trim()) {
        return res.status(400).json({ error: "Project title is required." });
    }

    try {
        const project = createProjectRecord({
            title: String(title).trim(),
            description: description ? String(description).trim() : "",
            client_id: clientId || null,
            location_lat: locationLat || null,
            location_lng: locationLng || null,
            address_label: addressLabel || null
        });

        return res.status(201).json({
            id: project.id,
            status: project.status
        });
    } catch (error) {
        return next(error);
    }
});

router.get("/:projectId", (req, res, next) => {
    try {
        const detail = getProjectDetail(req.params.projectId);

        if (detail) {
            return res.json(detail);
        }

        const fallbackDetail = buildProjectDetail(req.params.projectId);
        if (!fallbackDetail) {
            return res.status(404).json({ error: "Project not found." });
        }

        return res.json(fallbackDetail);
    } catch (error) {
        return next(error);
    }
});

router.patch("/:projectId", (req, res, next) => {
    try {
        const project = getProjectById(req.params.projectId) || getProjectByIdFromDb(req.params.projectId);
        if (!project) {
            return res.status(404).json({ error: "Project not found." });
        }

        const updated = updateProjectRecord(req.params.projectId, {
            title: req.body.title,
            description: req.body.description,
            status: req.body.status,
            property_type: req.body.propertyType,
            repair_scope: req.body.repairScope,
            location_lat: req.body.locationLat,
            location_lng: req.body.locationLng,
            address_label: req.body.addressLabel,
            client_id: req.body.clientId
        });

        if (!updated) {
            return res.status(404).json({ error: "Project not found." });
        }

        return res.json(updated);
    } catch (error) {
        return next(error);
    }
});

module.exports = router;
