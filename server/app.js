const express = require("express");
const cors = require("cors");
const path = require("node:path");
const projectRoutes = require("./routes/projectRoutes");
const photoRoutes = require("./routes/photoRoutes");
const analysisRoutes = require("./routes/analysisRoutes");
const quoteVariantRoutes = require("./routes/quoteVariantRoutes");
const materialCatalogRoutes = require("./routes/materialCatalogRoutes");
const supplierRoutes = require("./routes/supplierRoutes");
const { describeAnalysisProvider } = require("./ai/analysisService");
const { STORAGE_ROOT } = require("./storage/localPhotoStorage");

function createApp() {
    const app = express();
    const allowedOrigins = new Set([
        "http://localhost:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173"
    ]);

    app.use(cors({
        origin(origin, callback) {
            if (!origin || allowedOrigins.has(origin)) {
                callback(null, true);
                return;
            }

            callback(new Error("CORS origin not allowed."));
        },
        methods: ["GET", "POST", "PATCH", "PUT", "DELETE"]
    }));

    app.use(express.json());
    app.use("/mock-storage", express.static(path.resolve(STORAGE_ROOT)));

    app.get("/", (req, res) => {
        res.json({
            name: "NOVU Builder API",
            status: "ok",
            version: "mvp-skeleton"
        });
    });

    app.get("/api", (req, res) => {
        const analysisProvider = describeAnalysisProvider();

        res.json({
            message: "FotoNabidka MVP API",
            modules: ["projects", "photos", "analysis", "quote-variants", "material-catalog", "suppliers"],
            analysisProvider
        });
    });

    app.use("/api/projects", projectRoutes);
    app.use("/api/projects/:projectId/photos", photoRoutes);
    app.use("/api/projects/:projectId/analysis", analysisRoutes);
    app.use("/api/material-catalog", materialCatalogRoutes);
    app.use("/api/suppliers", supplierRoutes);
    app.use("/api", quoteVariantRoutes);

    app.use((err, req, res, next) => {
        if (err instanceof SyntaxError && "body" in err) {
            return res.status(400).json({ error: "Invalid JSON body." });
        }

        if (err.message === "CORS origin not allowed.") {
            return res.status(403).json({ error: "Origin is not allowed." });
        }

        return next(err);
    });

    app.use((req, res) => {
        res.status(404).json({ error: "Route not found." });
    });

    app.use((err, req, res, next) => {
        console.error(err.stack);
        res.status(500).json({ error: "Internal server error." });
    });

    return app;
}

if (require.main === module) {
    const PORT = process.env.PORT || 3000;
    const app = createApp();

    app.listen(PORT, () => {
        console.log(`Server running on http://localhost:${PORT}`);
    });
}

module.exports = { createApp };
