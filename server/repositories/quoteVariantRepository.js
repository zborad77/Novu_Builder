const path = require("path");
const { DatabaseSync } = require("node:sqlite");

const databasePath = path.resolve(__dirname, "../../prisma/dev.db");

function openDatabase() {
    const database = new DatabaseSync(databasePath);
    database.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL;");
    return database;
}

function mapVariant(row) {
    if (!row) {
        return null;
    }

    return {
        id: row.id,
        project_id: row.project_id,
        analysis_result_id: row.analysis_result_id,
        pricing_profile_id: row.pricing_profile_id,
        variant_type: row.variant_type,
        labor_cost: row.labor_cost,
        material_cost: row.material_cost,
        other_cost: row.other_cost,
        margin_pct: row.margin_pct,
        total_ex_vat: row.total_ex_vat,
        vat_amount: row.vat_amount,
        total_inc_vat: row.total_inc_vat,
        created_at: row.created_at,
        updated_at: row.updated_at
    };
}

function mapItem(row) {
    return {
        id: row.id,
        quote_variant_id: row.quote_variant_id,
        item_type: row.item_type,
        name: row.name,
        description: row.description,
        quantity: row.quantity,
        unit: row.unit,
        unit_price: row.unit_price,
        total_price: row.total_price,
        material_catalog_id: row.material_catalog_id,
        supplier_id: row.supplier_id,
        price_source: row.price_source,
        is_manual_override: Boolean(row.is_manual_override),
        ai_suggested_unit_price: row.ai_suggested_unit_price,
        supplier_reference_unit_price: row.supplier_reference_unit_price,
        company_default_unit_price: row.company_default_unit_price,
        sort_order: row.sort_order,
        created_at: row.created_at,
        updated_at: row.updated_at
    };
}

function parseJsonField(value) {
    if (!value) {
        return null;
    }

    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

function getAnalysisJobById(jobId) {
    const database = openDatabase();

    try {
        return database.prepare(`
            SELECT *
            FROM analysis_jobs
            WHERE id = ?
        `).get(jobId) || null;
    } finally {
        database.close();
    }
}

function listQuoteVariantsByProjectId(projectId) {
    const database = openDatabase();

    try {
        const variants = database.prepare(`
            SELECT *
            FROM quote_variants
            WHERE project_id = ?
            ORDER BY created_at ASC, id ASC
        `).all(projectId);

        return variants.map(row => {
            const variant = mapVariant(row);
            const items = database.prepare(`
                SELECT *
                FROM quote_items
                WHERE quote_variant_id = ?
                ORDER BY sort_order ASC, created_at ASC
            `).all(variant.id).map(mapItem);

            return {
                ...variant,
                items
            };
        });
    } finally {
        database.close();
    }
}

function roundCurrency(value) {
    return Math.round(value * 100) / 100;
}

function roundMeasure(value) {
    return Math.round((value + Number.EPSILON) * 1000) / 1000;
}

function getEffectiveAreaSqm(analysis) {
    const manualAreaSqm = Number(analysis.manual_area_sqm || 0);
    const estimatedAreaSqm = Number(analysis.estimated_area_sqm || 0);

    if (analysis.final_area_source === "manual" && manualAreaSqm > 0) {
        return manualAreaSqm;
    }

    return estimatedAreaSqm;
}

function recalculateQuoteVariants(projectId) {
    const database = openDatabase();

    try {
        database.exec("BEGIN IMMEDIATE");
        const project = database.prepare("SELECT * FROM projects WHERE id = ?").get(projectId);
        const analysis = database.prepare(`
            SELECT *
            FROM analysis_results
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        `).get(projectId);
        const pricingProfile = database.prepare(`
            SELECT *
            FROM pricing_profiles
            WHERE is_default = 1
            LIMIT 1
        `).get();

        if (!project || !analysis || !pricingProfile) {
            database.exec("ROLLBACK");
            return null;
        }

        const effectiveAreaSqm = getEffectiveAreaSqm(analysis);
        if (!effectiveAreaSqm) {
            database.exec("ROLLBACK");
            return null;
        }

        const suggestedMaterials = parseJsonField(analysis.materials_suggestion_json) || [];
        const materialNames = suggestedMaterials
            .map(item => String(item.name || "").trim().toLowerCase())
            .filter(Boolean);

        const matchedMaterials = materialNames.length > 0
            ? database.prepare(`
                SELECT *
                FROM material_catalog
                WHERE organization_id = ? AND is_active = 1
                  AND LOWER(name) IN (${materialNames.map(() => "?").join(", ")})
                ORDER BY name ASC
            `).all(project.organization_id, ...materialNames)
            : [];

        const existingVariants = database.prepare(`
            SELECT id
            FROM quote_variants
            WHERE project_id = ?
        `).all(projectId);

        existingVariants.forEach(variant => {
            database.prepare("DELETE FROM quote_items WHERE quote_variant_id = ?").run(variant.id);
        });
        database.prepare("DELETE FROM quote_variants WHERE project_id = ?").run(projectId);

        const timestamp = new Date().toISOString();
        const baseLabor = effectiveAreaSqm * pricingProfile.labor_hours_per_sqm * pricingProfile.hourly_rate;
        const materialLineBase = matchedMaterials.map(material => {
            const rawQuantity = effectiveAreaSqm * material.norm_per_sqm;
            const quantity = roundMeasure(rawQuantity);
            const unitPrice = Number(material.default_unit_price);
            const totalPrice = roundCurrency(rawQuantity * unitPrice);
            const suggestedMaterial = suggestedMaterials.find(item => String(item.name || "").trim().toLowerCase() === String(material.name || "").trim().toLowerCase());
            const supplierReference = database.prepare(`
                SELECT *
                FROM supplier_material_prices
                WHERE material_catalog_id = ?
                ORDER BY unit_price ASC, supplier_id ASC
                LIMIT 1
            `).get(material.id);

            return {
                material_catalog_id: material.id,
                supplier_id: material.default_supplier_id || supplierReference?.supplier_id || null,
                name: material.name,
                description: suggestedMaterial
                    ? `AI navrhla material ${material.name} pro opravu o plose ${effectiveAreaSqm} m2.`
                    : `Material z firemniho katalogu pro opravu o plose ${effectiveAreaSqm} m2.`,
                quantity,
                unit: material.unit,
                unit_price: unitPrice,
                total_price: totalPrice,
                ai_suggested_unit_price: suggestedMaterial?.quantity ? roundCurrency(totalPrice / suggestedMaterial.quantity) : null,
                supplier_reference_unit_price: supplierReference?.unit_price ?? null,
                company_default_unit_price: unitPrice
            };
        });
        const baseMaterial = roundCurrency(materialLineBase.reduce((sum, item) => sum + item.total_price, 0));
        const baseOther = 3500;
        const variantsConfig = [
            { type: "economy", laborFactor: 1, materialFactor: 1, otherFactor: 1, margin: pricingProfile.margin_economy_pct },
            { type: "standard", laborFactor: 1.12, materialFactor: 1.28, otherFactor: 1.08, margin: pricingProfile.margin_standard_pct },
            { type: "premium", laborFactor: 1.22, materialFactor: 1.6, otherFactor: 1.18, margin: pricingProfile.margin_premium_pct }
        ];

        const createdVariants = variantsConfig.map((config, index) => {
            const laborCost = roundCurrency(baseLabor * config.laborFactor);
            const materialCost = roundCurrency(baseMaterial * config.materialFactor);
            const otherCost = roundCurrency(baseOther * config.otherFactor);
            const subtotal = laborCost + materialCost + otherCost;
            const totalExVat = roundCurrency(subtotal * (1 + config.margin / 100));
            const vatAmount = roundCurrency(totalExVat * (pricingProfile.vat_pct / 100));
            const variantId = `qv_${Date.now()}_${index + 1}`;

            database.prepare(`
                INSERT INTO quote_variants (
                    id, project_id, analysis_result_id, pricing_profile_id, variant_type,
                    labor_cost, material_cost, other_cost, margin_pct,
                    total_ex_vat, vat_amount, total_inc_vat, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            `).run(
                variantId,
                projectId,
                analysis.id,
                pricingProfile.id,
                config.type,
                laborCost,
                materialCost,
                otherCost,
                config.margin,
                totalExVat,
                vatAmount,
                roundCurrency(totalExVat + vatAmount),
                timestamp,
                timestamp
            );

            const items = [
                {
                    id: `qi_${Date.now()}_${index + 1}_1`,
                    item_type: "labor",
                    name: "Prace",
                    description: `Prace podle plochy opravy ${effectiveAreaSqm} m2 a firemni normy.`,
                    quantity: roundCurrency(effectiveAreaSqm * pricingProfile.labor_hours_per_sqm * config.laborFactor),
                    unit: "hod",
                    unit_price: pricingProfile.hourly_rate,
                    total_price: laborCost,
                    material_catalog_id: null,
                    supplier_id: null,
                    price_source: "company_catalog",
                    is_manual_override: 0,
                    ai_suggested_unit_price: null,
                    supplier_reference_unit_price: null,
                    company_default_unit_price: pricingProfile.hourly_rate,
                    sort_order: 1
                },
                {
                    id: `qi_${Date.now()}_${index + 1}_999`,
                    item_type: "other",
                    name: "Vedlejsi naklady",
                    description: "Doprava, priprava, drobny material",
                    quantity: 1,
                    unit: "ks",
                    unit_price: otherCost,
                    total_price: otherCost,
                    material_catalog_id: null,
                    supplier_id: null,
                    price_source: "company_catalog",
                    is_manual_override: 0,
                    ai_suggested_unit_price: null,
                    supplier_reference_unit_price: null,
                    company_default_unit_price: otherCost,
                    sort_order: 999
                }
            ];

            materialLineBase.forEach((item, itemIndex) => {
                items.splice(itemIndex + 1, 0, {
                    id: `qi_${Date.now()}_${index + 1}_${itemIndex + 2}`,
                    item_type: "material",
                    name: item.name,
                    description: item.description,
                    quantity: roundMeasure(item.quantity * config.materialFactor),
                    unit: item.unit,
                    unit_price: item.unit_price,
                    total_price: roundCurrency(item.total_price * config.materialFactor),
                    material_catalog_id: item.material_catalog_id,
                    supplier_id: item.supplier_id,
                    price_source: "company_catalog",
                    is_manual_override: 0,
                    ai_suggested_unit_price: item.ai_suggested_unit_price,
                    supplier_reference_unit_price: item.supplier_reference_unit_price,
                    company_default_unit_price: item.company_default_unit_price,
                    sort_order: itemIndex + 2
                });
            });

            items.forEach(item => {
                database.prepare(`
                    INSERT INTO quote_items (
                        id, quote_variant_id, item_type, name, description,
                        quantity, unit, unit_price, total_price, material_catalog_id,
                        supplier_id, price_source, is_manual_override, ai_suggested_unit_price,
                        supplier_reference_unit_price, company_default_unit_price, sort_order, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                `).run(
                    item.id,
                    variantId,
                    item.item_type,
                    item.name,
                    item.description,
                    item.quantity,
                    item.unit,
                    item.unit_price,
                    item.total_price,
                    item.material_catalog_id,
                    item.supplier_id,
                    item.price_source,
                    item.is_manual_override,
                    item.ai_suggested_unit_price,
                    item.supplier_reference_unit_price,
                    item.company_default_unit_price,
                    item.sort_order,
                    timestamp,
                    timestamp
                );
            });

            return {
                id: variantId,
                variant_type: config.type,
                total_inc_vat: roundCurrency(totalExVat + vatAmount)
            };
        });

        database.prepare(`
            UPDATE projects
            SET status = ?, updated_at = ?
            WHERE id = ?
        `).run("quoted", timestamp, projectId);

        database.exec("COMMIT");
        return createdVariants;
    } catch (error) {
        try {
            database.exec("ROLLBACK");
        } catch {
            // no-op
        }
        throw error;
    } finally {
        database.close();
    }
}

function updateQuoteVariantRecord(variantId, changes) {
    const database = openDatabase();

    try {
        const variant = database.prepare(`
            SELECT *
            FROM quote_variants
            WHERE id = ?
        `).get(variantId);

        if (!variant) {
            return null;
        }

        const laborCost = changes.labor_cost ?? variant.labor_cost;
        const materialCost = changes.material_cost ?? variant.material_cost;
        const otherCost = changes.other_cost ?? variant.other_cost;
        const marginPct = changes.margin_pct ?? variant.margin_pct;
        const totalExVat = roundCurrency((laborCost + materialCost + otherCost) * (1 + marginPct / 100));
        const vatAmount = roundCurrency(totalExVat * 0.21);
        const totalIncVat = roundCurrency(totalExVat + vatAmount);
        const timestamp = new Date().toISOString();

        database.prepare(`
            UPDATE quote_variants
            SET labor_cost = ?, material_cost = ?, other_cost = ?, margin_pct = ?,
                total_ex_vat = ?, vat_amount = ?, total_inc_vat = ?, updated_at = ?
            WHERE id = ?
        `).run(
            laborCost,
            materialCost,
            otherCost,
            marginPct,
            totalExVat,
            vatAmount,
            totalIncVat,
            timestamp,
            variantId
        );

        const updated = database.prepare(`
            SELECT *
            FROM quote_variants
            WHERE id = ?
        `).get(variantId);

        return mapVariant(updated);
    } finally {
        database.close();
    }
}

module.exports = {
    getAnalysisJobById,
    listQuoteVariantsByProjectId,
    recalculateQuoteVariants,
    updateQuoteVariantRecord
};
