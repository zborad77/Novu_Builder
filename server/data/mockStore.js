const now = new Date().toISOString();

const pricingProfiles = [
    {
        id: "price_default",
        organization_id: "org_1",
        name: "Default profile",
        hourly_rate: 520,
        daily_rate: 4200,
        margin_economy_pct: 12,
        margin_standard_pct: 18,
        margin_premium_pct: 28,
        vat_pct: 21,
        currency: "CZK",
        is_default: true,
        created_at: now,
        updated_at: now
    }
];

const clients = [
    {
        id: "cli_1",
        organization_id: "org_1",
        full_name: "Petr Novak",
        company_name: "",
        email: "petr.novak@example.com",
        phone: "+420777111222",
        notes: "",
        created_at: now,
        updated_at: now
    }
];

const projects = [
    {
        id: "prj_1",
        organization_id: "org_1",
        client_id: "cli_1",
        created_by_user_id: "usr_1",
        title: "Fasada domu Novak",
        description: "Znecistena severni stena a lokalni praskliny kolem oken.",
        status: "analysed",
        property_type: "facade",
        repair_scope: "local_repair",
        location_lat: 50.087,
        location_lng: 14.421,
        address_label: "Praha 1",
        created_at: now,
        updated_at: now
    }
];

const projectPhotos = [
    {
        id: "pho_1",
        project_id: "prj_1",
        storage_key: "projects/prj_1/front-view.jpg",
        original_filename: "front-view.jpg",
        mime_type: "image/jpeg",
        file_size: 2450000,
        width: 1600,
        height: 1200,
        taken_at: now,
        exif_lat: 50.087,
        exif_lng: 14.421,
        sort_order: 1,
        created_at: now
    }
];

const analysisJobs = [
    {
        id: "job_1",
        project_id: "prj_1",
        status: "completed",
        job_type: "initial_review",
        requested_by_user_id: "usr_1",
        started_at: now,
        finished_at: now,
        error_message: null,
        created_at: now
    }
];

const analysisResults = [
    {
        id: "ana_1",
        project_id: "prj_1",
        analysis_job_id: "job_1",
        object_type: "facade",
        surface_condition: "damaged",
        recommended_scope: "local_repair",
        estimated_area_sqm: 42.5,
        area_confidence: 0.72,
        mask_polygon_json: [
            { x: 0.1, y: 0.2 },
            { x: 0.82, y: 0.18 },
            { x: 0.86, y: 0.84 },
            { x: 0.14, y: 0.88 }
        ],
        materials_suggestion_json: [
            { name: "Penetrace", unit: "l", quantity: 18 },
            { name: "Opravna smes", unit: "kg", quantity: 120 }
        ],
        workflow_suggestion_json: [
            "Ocistit povrch",
            "Lokalne opravit praskliny",
            "Aplikovat finalni nater"
        ],
        model_name: "mock-vision",
        model_version: "0.1",
        created_at: now
    }
];

const quoteVariants = [
    {
        id: "qv_1",
        project_id: "prj_1",
        analysis_result_id: "ana_1",
        pricing_profile_id: "price_default",
        variant_type: "economy",
        labor_cost: 16800,
        material_cost: 13800,
        other_cost: 4200,
        margin_pct: 12,
        total_ex_vat: 38976,
        vat_amount: 8184.96,
        total_inc_vat: 47160.96,
        created_at: now,
        updated_at: now
    },
    {
        id: "qv_2",
        project_id: "prj_1",
        analysis_result_id: "ana_1",
        pricing_profile_id: "price_default",
        variant_type: "standard",
        labor_cost: 19320,
        material_cost: 18630,
        other_cost: 4700,
        margin_pct: 18,
        total_ex_vat: 50248.6,
        vat_amount: 10552.21,
        total_inc_vat: 60800.81,
        created_at: now,
        updated_at: now
    },
    {
        id: "qv_3",
        project_id: "prj_1",
        analysis_result_id: "ana_1",
        pricing_profile_id: "price_default",
        variant_type: "premium",
        labor_cost: 21840,
        material_cost: 24840,
        other_cost: 5500,
        margin_pct: 28,
        total_ex_vat: 66890.2,
        vat_amount: 14046.94,
        total_inc_vat: 80937.14,
        created_at: now,
        updated_at: now
    }
];

const quoteItems = [
    {
        id: "qi_1",
        quote_variant_id: "qv_1",
        item_type: "labor",
        name: "Cisteni a oprava fasady",
        description: "Zakladni pracovni rozsah",
        quantity: 42.5,
        unit: "m2",
        unit_price: 395.29,
        total_price: 16800,
        sort_order: 1,
        created_at: now
    }
];

const counters = {
    project: 2,
    photo: 2,
    job: 2,
    analysis: 2,
    quoteVariant: 4,
    quoteItem: 2
};

function nextId(type) {
    const prefixes = {
        project: "prj",
        photo: "pho",
        job: "job",
        analysis: "ana",
        quoteVariant: "qv",
        quoteItem: "qi"
    };

    const value = counters[type];
    counters[type] += 1;
    return `${prefixes[type]}_${value}`;
}

function getProjectById(projectId) {
    return projects.find(project => project.id === projectId);
}

function getClientById(clientId) {
    return clients.find(client => client.id === clientId);
}

function getPhotosByProjectId(projectId) {
    return projectPhotos
        .filter(photo => photo.project_id === projectId)
        .sort((left, right) => left.sort_order - right.sort_order);
}

function getAnalysisJobsByProjectId(projectId) {
    return analysisJobs.filter(job => job.project_id === projectId);
}

function getLatestAnalysisResult(projectId) {
    return analysisResults
        .filter(result => result.project_id === projectId)
        .sort((left, right) => new Date(right.created_at) - new Date(left.created_at))[0] || null;
}

function getQuoteVariantsByProjectId(projectId) {
    return quoteVariants.filter(variant => variant.project_id === projectId);
}

function getQuoteItemsByVariantId(variantId) {
    return quoteItems.filter(item => item.quote_variant_id === variantId);
}

function buildProjectSummary(project) {
    const latestAnalysis = getLatestAnalysisResult(project.id);
    const variants = getQuoteVariantsByProjectId(project.id);
    return {
        id: project.id,
        title: project.title,
        status: project.status,
        propertyType: project.property_type,
        repairScope: project.repair_scope,
        addressLabel: project.address_label,
        photoCount: getPhotosByProjectId(project.id).length,
        estimatedAreaSqm: latestAnalysis ? latestAnalysis.estimated_area_sqm : null,
        latestQuoteTotal: variants.length > 0 ? variants[0].total_inc_vat : null,
        updatedAt: project.updated_at
    };
}

function buildProjectDetail(projectId) {
    const project = getProjectById(projectId);
    if (!project) {
        return null;
    }

    const client = project.client_id ? getClientById(project.client_id) : null;
    const photos = getPhotosByProjectId(projectId).map(photo => ({
        id: photo.id,
        originalFilename: photo.original_filename,
        storageKey: photo.storage_key,
        mimeType: photo.mime_type,
        width: photo.width,
        height: photo.height,
        sortOrder: photo.sort_order,
        url: `/mock-storage/${photo.storage_key}`
    }));
    const latestAnalysis = getLatestAnalysisResult(projectId);
    const variants = getQuoteVariantsByProjectId(projectId).map(variant => ({
        ...variant,
        items: getQuoteItemsByVariantId(variant.id)
    }));

    return {
        id: project.id,
        title: project.title,
        description: project.description,
        status: project.status,
        propertyType: project.property_type,
        repairScope: project.repair_scope,
        location: {
            lat: project.location_lat,
            lng: project.location_lng,
            addressLabel: project.address_label
        },
        client,
        photos,
        latestAnalysis,
        quoteVariants: variants,
        createdAt: project.created_at,
        updatedAt: project.updated_at
    };
}

function createProject(data) {
    const timestamp = new Date().toISOString();
    const project = {
        id: nextId("project"),
        organization_id: data.organization_id || "org_1",
        client_id: data.client_id || null,
        created_by_user_id: data.created_by_user_id || "usr_1",
        title: data.title,
        description: data.description || "",
        status: "draft",
        property_type: data.property_type || null,
        repair_scope: data.repair_scope || null,
        location_lat: data.location_lat || null,
        location_lng: data.location_lng || null,
        address_label: data.address_label || null,
        created_at: timestamp,
        updated_at: timestamp
    };

    projects.push(project);
    return project;
}

function updateProject(projectId, changes) {
    const project = getProjectById(projectId);
    if (!project) {
        return null;
    }

    const allowed = [
        "title",
        "description",
        "status",
        "property_type",
        "repair_scope",
        "location_lat",
        "location_lng",
        "address_label",
        "client_id"
    ];

    allowed.forEach(key => {
        if (Object.prototype.hasOwnProperty.call(changes, key)) {
            project[key] = changes[key];
        }
    });

    project.updated_at = new Date().toISOString();
    return project;
}

function addPhoto(projectId, input) {
    const photo = {
        id: nextId("photo"),
        project_id: projectId,
        storage_key: input.storage_key,
        original_filename: input.original_filename,
        mime_type: input.mime_type || "image/jpeg",
        file_size: input.file_size || 0,
        width: input.width || null,
        height: input.height || null,
        taken_at: input.taken_at || new Date().toISOString(),
        exif_lat: input.exif_lat || null,
        exif_lng: input.exif_lng || null,
        sort_order: input.sort_order || getPhotosByProjectId(projectId).length + 1,
        created_at: new Date().toISOString()
    };

    projectPhotos.push(photo);
    updateProject(projectId, { status: "uploaded" });
    return photo;
}

function removePhoto(projectId, photoId) {
    const index = projectPhotos.findIndex(photo => photo.id === photoId && photo.project_id === projectId);
    if (index === -1) {
        return false;
    }

    projectPhotos.splice(index, 1);
    return true;
}

function createMockAnalysis(projectId) {
    const project = getProjectById(projectId);
    if (!project) {
        return null;
    }

    const timestamp = new Date().toISOString();
    const job = {
        id: nextId("job"),
        project_id: projectId,
        status: "completed",
        job_type: "manual_trigger",
        requested_by_user_id: "usr_1",
        started_at: timestamp,
        finished_at: timestamp,
        error_message: null,
        created_at: timestamp
    };

    analysisJobs.push(job);

    const area = project.description && project.description.toLowerCase().includes("strecha") ? 68.2 : 39.8;
    const objectType = project.description && project.description.toLowerCase().includes("strecha") ? "roof" : "facade";
    const scope = project.description && project.description.toLowerCase().includes("cist") ? "cleaning" : "local_repair";
    const result = {
        id: nextId("analysis"),
        project_id: projectId,
        analysis_job_id: job.id,
        object_type: objectType,
        surface_condition: "requires_attention",
        recommended_scope: scope,
        estimated_area_sqm: area,
        area_confidence: 0.64,
        mask_polygon_json: [
            { x: 0.12, y: 0.16 },
            { x: 0.84, y: 0.17 },
            { x: 0.88, y: 0.86 },
            { x: 0.14, y: 0.87 }
        ],
        materials_suggestion_json: [
            { name: "Penetrace", unit: "l", quantity: Math.round(area * 0.35) },
            { name: "Fasadni nater", unit: "kg", quantity: Math.round(area * 0.45) }
        ],
        workflow_suggestion_json: [
            "Vizualni kontrola povrchu",
            "Ocisteni a priprava podkladu",
            "Oprava a finalni vrstva"
        ],
        model_name: "mock-vision",
        model_version: "0.1",
        created_at: timestamp
    };

    analysisResults.push(result);
    updateProject(projectId, {
        status: "analysed",
        property_type: objectType,
        repair_scope: scope
    });

    return { job, result };
}

function getAnalysisJobById(jobId) {
    return analysisJobs.find(job => job.id === jobId) || null;
}

function roundCurrency(value) {
    return Math.round(value * 100) / 100;
}

function recalculateQuoteVariants(projectId) {
    const project = getProjectById(projectId);
    const analysis = getLatestAnalysisResult(projectId);
    const pricingProfile = pricingProfiles.find(profile => profile.is_default);

    if (!project || !analysis || !pricingProfile) {
        return null;
    }

    const baseLabor = analysis.estimated_area_sqm * pricingProfile.hourly_rate * 0.75;
    const baseMaterial = analysis.estimated_area_sqm * 320;
    const baseOther = 3500;

    const variantConfigs = [
        { variant_type: "economy", laborFactor: 1, materialFactor: 1, otherFactor: 1, margin: pricingProfile.margin_economy_pct },
        { variant_type: "standard", laborFactor: 1.12, materialFactor: 1.28, otherFactor: 1.08, margin: pricingProfile.margin_standard_pct },
        { variant_type: "premium", laborFactor: 1.22, materialFactor: 1.6, otherFactor: 1.18, margin: pricingProfile.margin_premium_pct }
    ];

    for (let index = quoteVariants.length - 1; index >= 0; index -= 1) {
        if (quoteVariants[index].project_id === projectId) {
            quoteVariants.splice(index, 1);
        }
    }

    for (let index = quoteItems.length - 1; index >= 0; index -= 1) {
        const variantId = quoteItems[index].quote_variant_id;
        if (variantId.startsWith("qv_")) {
            const belongsToProject = quoteVariants.some(variant => variant.id === variantId && variant.project_id === projectId);
            if (!belongsToProject) {
                quoteItems.splice(index, 1);
            }
        }
    }

    const createdVariants = variantConfigs.map((config, orderIndex) => {
        const laborCost = roundCurrency(baseLabor * config.laborFactor);
        const materialCost = roundCurrency(baseMaterial * config.materialFactor);
        const otherCost = roundCurrency(baseOther * config.otherFactor);
        const subtotal = laborCost + materialCost + otherCost;
        const totalExVat = roundCurrency(subtotal * (1 + config.margin / 100));
        const vatAmount = roundCurrency(totalExVat * (pricingProfile.vat_pct / 100));
        const timestamp = new Date().toISOString();
        const variant = {
            id: nextId("quoteVariant"),
            project_id: projectId,
            analysis_result_id: analysis.id,
            pricing_profile_id: pricingProfile.id,
            variant_type: config.variant_type,
            labor_cost: laborCost,
            material_cost: materialCost,
            other_cost: otherCost,
            margin_pct: config.margin,
            total_ex_vat: totalExVat,
            vat_amount: vatAmount,
            total_inc_vat: roundCurrency(totalExVat + vatAmount),
            created_at: timestamp,
            updated_at: timestamp
        };

        quoteVariants.push(variant);

        const items = [
            { item_type: "labor", name: "Prace", description: "Odhad prace dle rozsahu", quantity: analysis.estimated_area_sqm, unit: "m2", unit_price: roundCurrency(laborCost / analysis.estimated_area_sqm), total_price: laborCost, sort_order: 1 },
            { item_type: "material", name: "Material", description: "Navrzene materialy pro variantu", quantity: analysis.estimated_area_sqm, unit: "m2", unit_price: roundCurrency(materialCost / analysis.estimated_area_sqm), total_price: materialCost, sort_order: 2 },
            { item_type: "other", name: "Vedlejsi naklady", description: "Doprava, priprava, drobny material", quantity: 1, unit: "ks", unit_price: otherCost, total_price: otherCost, sort_order: 3 }
        ];

        items.forEach(item => {
            quoteItems.push({
                id: nextId("quoteItem"),
                quote_variant_id: variant.id,
                created_at: timestamp,
                ...item
            });
        });

        return {
            ...variant,
            orderIndex
        };
    });

    updateProject(projectId, { status: "quoted" });
    return createdVariants;
}

function updateQuoteVariant(variantId, changes) {
    const variant = quoteVariants.find(entry => entry.id === variantId);
    if (!variant) {
        return null;
    }

    const allowed = ["labor_cost", "material_cost", "other_cost", "margin_pct"];
    allowed.forEach(key => {
        if (Object.prototype.hasOwnProperty.call(changes, key)) {
            variant[key] = Number(changes[key]);
        }
    });

    const totalExVat = roundCurrency((variant.labor_cost + variant.material_cost + variant.other_cost) * (1 + variant.margin_pct / 100));
    variant.total_ex_vat = totalExVat;
    variant.vat_amount = roundCurrency(totalExVat * 0.21);
    variant.total_inc_vat = roundCurrency(variant.total_ex_vat + variant.vat_amount);
    variant.updated_at = new Date().toISOString();

    return variant;
}

module.exports = {
    clients,
    projects,
    projectPhotos,
    analysisJobs,
    analysisResults,
    pricingProfiles,
    quoteVariants,
    quoteItems,
    buildProjectSummary,
    buildProjectDetail,
    createProject,
    updateProject,
    getProjectById,
    getPhotosByProjectId,
    addPhoto,
    removePhoto,
    createMockAnalysis,
    getLatestAnalysisResult,
    getAnalysisJobById,
    getQuoteVariantsByProjectId,
    getQuoteItemsByVariantId,
    recalculateQuoteVariants,
    updateQuoteVariant
};
