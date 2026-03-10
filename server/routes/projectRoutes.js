

const express = require("express");
const router = express.Router();

let projects = [
    {
        id: Date.now(),
        name: "Zakázka dům Novák",
        area: 120,
        price: 35000
    }
];

// Načtení všech projektů
router.get("/", (req, res) => {
    res.json(projects);
});

// Vytvoření nového projektu
router.post("/", (req, res) => {
    const { name, area, price } = req.body;

    // Validace vstupů
    if (!name || !area || !price || area <= 0 || price <= 0) {
        return res.status(400).json({ error: "Neplatná data – vyplňte název, plochu a cenu." });
    }

    const newProject = {
        id: Date.now(),
        name: name,
        area: parseFloat(area),
        price: parseFloat(price)
    };

    projects.push(newProject);
    res.status(201).json(newProject);
});

// Úprava projektu
router.put("/:id", (req, res) => {
    const id = parseInt(req.params.id);
    const { name, area, price } = req.body;

    const index = projects.findIndex(p => p.id === id);

    if (index === -1) {
        return res.status(404).json({ error: "Projekt nenalezen." });
    }

    if (!name || !area || !price || area <= 0 || price <= 0) {
        return res.status(400).json({ error: "Neplatná data." });
    }

    projects[index] = {
        id: id,
        name: name,
        area: parseFloat(area),
        price: parseFloat(price)
    };

    res.json(projects[index]);
});

// Smazání projektu
router.delete("/:id", (req, res) => {
    const id = parseInt(req.params.id);

    const index = projects.findIndex(p => p.id === id);

    if (index === -1) {
        return res.status(404).json({ error: "Projekt nenalezen." });
    }

    projects.splice(index, 1);
    res.json({ message: "Projekt smazán." });
});

module.exports = router;