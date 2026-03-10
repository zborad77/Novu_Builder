
const express = require("express");
const cors = require("cors");
const projectRoutes = require("./routes/projectRoutes");

const app = express();

// Bezpečnější CORS - povolí jen frontend na localhostu
app.use(cors({
    origin: "http://localhost:5500", // uprav na port tvého frontendu
    methods: ["GET", "POST", "PUT", "DELETE"]
}));

app.use(express.json());

// Ošetření chybného JSON v požadavku
app.use((err, req, res, next) => {
    if (err.type === "entity.parse.failed") {
        return res.status(400).json({ error: "Neplatný formát JSON." });
    }
    next(err);
});

app.get("/", (req, res) => {
    res.send("NOVU Builder server běží");
});

app.use("/projects", projectRoutes);

// Ošetření neexistující adresy (404)
app.use((req, res) => {
    res.status(404).json({ error: "Stránka nenalezena." });
});

// Globální error handler
app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(500).json({ error: "Chyba serveru." });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server běží na http://localhost:${PORT}`);
});