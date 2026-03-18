"use strict";

function buildMockMask() {
    return [
        { x: 0.12, y: 0.16 },
        { x: 0.84, y: 0.17 },
        { x: 0.88, y: 0.86 },
        { x: 0.14, y: 0.87 }
    ];
}

function countByOrientation(photos, orientation) {
    return photos.filter(photo => photo.orientation === orientation).length;
}

function analyzeProject({ project, photos = [] }) {
    const description = String(project.description || "").toLowerCase();
    const address = String(project.address_label || "").toLowerCase();
    const normalizedText = `${description} ${address}`;
    const photoCount = photos.length || 1;
    const gpsPhotoCount = photos.filter(photo => photo.hasGps).length;
    const portraitCount = countByOrientation(photos, "portrait");
    const landscapeCount = countByOrientation(photos, "landscape");
    const hasCloseups = photos.some(photo => photo.orientation === "portrait" || (photo.width && photo.width < 1200));
    const hasWideCoverage = landscapeCount >= 2 || photoCount >= 3;
    const isRoof = description.includes("strecha") || address.includes("strecha");
    const isCleaning =
        normalizedText.includes("cisteni") ||
        normalizedText.includes("ocisteni") ||
        normalizedText.includes("myti");
    const objectType = isRoof ? "roof" : "facade";
    const recommendedScope = isCleaning
        ? "cleaning"
        : hasCloseups
            ? "local_repair"
            : hasWideCoverage
                ? "full_reconstruction"
                : "local_repair";
    const baseArea = isRoof ? 52 : 28;
    const photoAreaBoost = isRoof ? photoCount * 6.5 : photoCount * 7.5;
    const orientationBoost = landscapeCount * 1.4 + portraitCount * 0.9;
    const gpsBoost = gpsPhotoCount * 0.6;
    const estimatedAreaSqm = baseArea + photoAreaBoost + orientationBoost + gpsBoost;
    const areaConfidence = Math.min(
        0.52 + photoCount * 0.05 + gpsPhotoCount * 0.03 + landscapeCount * 0.02,
        0.93
    );

    return {
        providerKey: "mock",
        jobType: "vision_mock",
        objectType,
        surfaceCondition: "requires_attention",
        recommendedScope,
        estimatedAreaSqm: Number(estimatedAreaSqm.toFixed(1)),
        areaConfidence: Number(areaConfidence.toFixed(2)),
        maskPolygon: buildMockMask(),
        materials: isCleaning
            ? [
                { name: "Penetrace", unit: "l", quantity: Math.round(estimatedAreaSqm * 0.22) },
                { name: "Fasadni nater", unit: "kg", quantity: Math.round(estimatedAreaSqm * 0.28) }
            ]
            : [
                { name: "Penetrace", unit: "l", quantity: Math.round(estimatedAreaSqm * 0.35) },
                { name: "Opravna smes", unit: "kg", quantity: Math.round(estimatedAreaSqm * 2.8) }
            ],
        workflow: [
            "Vizualni kontrola povrchu",
            "Ocisteni a priprava podkladu",
            isCleaning ? "Aplikace cistici a ochranne vrstvy" : "Lokalni oprava a finalni vrstva"
        ],
        modelName: "mock-vision",
        modelVersion: "0.2"
    };
}

module.exports = {
    key: "mock",
    analyzeProject
};
