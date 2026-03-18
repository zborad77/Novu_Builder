const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { createApp } = require('../server/app')
const { bootstrapDatabase } = require('../scripts/bootstrap_sqlite_db')
const { STORAGE_ROOT } = require('../server/storage/localPhotoStorage')

process.env.AI_ANALYSIS_PROVIDER = 'mock'

async function startServer() {
  const app = createApp()

  return await new Promise(resolve => {
    const server = app.listen(0, () => {
      const { port } = server.address()
      resolve({ server, port })
    })
  })
}

async function requestJson(port, path, options) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, options)
  const body = await response.json()

  return { response, body }
}

async function testProjectsEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects')

    assert.equal(response.status, 200)
    assert.ok(Array.isArray(body.items))
    assert.equal(body.items.length, 1)
    assert.equal(body.items[0].id, 'prj_1')
    assert.equal(body.items[0].title, 'Fasada domu Novak')
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testAnalysisEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects/prj_1/analysis')

    assert.equal(response.status, 200)
    assert.equal(body.project_id, 'prj_1')
    assert.equal(body.object_type, 'facade')
    assert.equal(body.recommended_scope, 'local_repair')
    assert.equal(body.estimated_area_sqm, 42.5)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testAnalysisTriggerUsesConfiguredProvider() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects/prj_1/analysis', {
      method: 'POST'
    })

    assert.equal(response.status, 202)
    assert.equal(body.status, 'completed')
    assert.equal(body.provider, 'mock')
    assert.equal(body.modelName, 'mock-vision')
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testAnalysisUsesPhotoMetadataAsInput() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const uploadResult = await requestJson(port, '/api/projects/prj_1/photos', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        files: [
          {
            originalFilename: 'detail-crack.jpg',
            mimeType: 'image/jpeg',
            width: 900,
            height: 1400,
            takenAt: '2026-03-17T10:00:00.000Z',
            exifLat: 50.0871,
            exifLng: 14.4211
          }
        ]
      })
    })

    assert.equal(uploadResult.response.status, 201)

    const analysisResult = await requestJson(port, '/api/projects/prj_1/analysis', {
      method: 'POST'
    })

    assert.equal(analysisResult.response.status, 202)

    const latestAnalysis = await requestJson(port, '/api/projects/prj_1/analysis')

    assert.equal(latestAnalysis.response.status, 200)
    assert.equal(latestAnalysis.body.estimated_area_sqm, 65)
    assert.equal(latestAnalysis.body.area_confidence, 0.88)
    assert.equal(latestAnalysis.body.recommended_scope, 'local_repair')
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testAnalysisManualAreaPatchEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects/prj_1/analysis', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        referencePhotoId: 'pho_1',
        selectedRepairPolygon: [
          { x: 0.18, y: 0.22 },
          { x: 0.47, y: 0.23 },
          { x: 0.46, y: 0.54 },
          { x: 0.19, y: 0.55 }
        ],
        manualAreaSqm: 11.5,
        finalAreaSource: 'manual'
      })
    })

    assert.equal(response.status, 200)
    assert.equal(body.reference_photo_id, 'pho_1')
    assert.equal(body.manual_area_sqm, 11.5)
    assert.equal(body.final_area_source, 'manual')
    assert.equal(body.selected_repair_polygon_json.length, 4)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testPhotosEndpointReturnsPrimaryAndMinimumMeta() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects/prj_1/photos')

    assert.equal(response.status, 200)
    assert.equal(body.items.length, 3)
    assert.equal(body.meta.minimumRecommendedCount, 3)
    assert.equal(body.meta.hasMinimumCount, true)
    assert.equal(body.meta.primaryPhotoId, 'pho_1')
    assert.equal(body.meta.derivativeStrategy.preview, 'ui-optimized-max-edge-1600')
    assert.equal(body.items.filter(item => item.isPrimary).length, 1)
    assert.equal(body.items[0].processingStatus, 'ready')
    assert.equal(body.items[0].variants.preview.width, 1600)
    assert.equal(body.items[0].variants.aiInput.width, 1280)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testPhotoUploadCreatesPreviewAndAiInputVariants() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects/prj_1/photos', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        files: [
          {
            originalFilename: 'north-wall.jpg',
            mimeType: 'image/jpeg',
            fileSize: 4000000,
            width: 4032,
            height: 3024
          }
        ]
      })
    })

    assert.equal(response.status, 201)
    assert.equal(body.uploaded.length, 1)
    assert.equal(body.uploaded[0].processingStatus, 'ready')
    assert.equal(body.uploaded[0].variants.preview.storageKey, 'projects/prj_1/preview/north-wall.jpg')
    assert.equal(body.uploaded[0].variants.aiInput.storageKey, 'projects/prj_1/ai/north-wall.jpg')

    const photosAfter = await requestJson(port, '/api/projects/prj_1/photos')
    const uploadedPhoto = photosAfter.body.items.find(item => item.originalFilename === 'north-wall.jpg')

    assert.ok(uploadedPhoto)
    assert.equal(uploadedPhoto.variants.preview.width, 1600)
    assert.equal(uploadedPhoto.variants.preview.height, 1200)
    assert.equal(uploadedPhoto.variants.aiInput.width, 1280)
    assert.equal(uploadedPhoto.variants.aiInput.height, 960)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testMultipartPhotoUploadStoresOriginalFileLocally() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const formData = new FormData()
    const fileBlob = new Blob(['fake-binary-image-content'], { type: 'image/jpeg' })

    formData.append('files', fileBlob, 'mobile-capture.jpg')
    formData.append('isPrimary', 'true')

    const response = await fetch(`http://127.0.0.1:${port}/api/projects/prj_1/photos`, {
      method: 'POST',
      body: formData
    })
    const body = await response.json()

    assert.equal(response.status, 201)
    assert.equal(body.uploaded.length, 1)
    assert.equal(body.uploaded[0].processingStatus, 'original_uploaded')
    assert.match(body.uploaded[0].storageKey, /^projects\/prj_1\/\d+-[a-f0-9]{8}-mobile-capture\.jpg$/)

    const absolutePath = path.join(STORAGE_ROOT, body.uploaded[0].storageKey)
    assert.equal(fs.existsSync(absolutePath), true)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testSetPrimaryPhotoEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects/prj_1/photos/pho_2/primary', {
      method: 'PATCH'
    })

    assert.equal(response.status, 200)
    assert.equal(body.photo.id, 'pho_2')
    assert.equal(body.photo.isPrimary, true)

    const photosAfter = await requestJson(port, '/api/projects/prj_1/photos')

    assert.equal(photosAfter.response.status, 200)
    assert.equal(photosAfter.body.meta.primaryPhotoId, 'pho_2')
    assert.equal(photosAfter.body.items.filter(item => item.isPrimary).length, 1)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testQuoteVariantsEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects/prj_1/quote-variants')

    assert.equal(response.status, 200)
    assert.ok(Array.isArray(body.items))
    assert.equal(body.items.length, 3)
    assert.deepEqual(
      body.items.map(item => item.variant_type).sort(),
      ['economy', 'premium', 'standard']
    )
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testQuoteRecalculationUsesAreaBasedPricing() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const recalcResponse = await requestJson(port, '/api/projects/prj_1/quote-variants/recalculate', {
      method: 'POST'
    })

    assert.equal(recalcResponse.response.status, 200)

    const { response, body } = await requestJson(port, '/api/projects/prj_1/quote-variants')

    assert.equal(response.status, 200)
    assert.equal(body.items.length, 3)

    const economy = body.items.find(item => item.variant_type === 'economy')
    assert.ok(economy)
    assert.equal(economy.labor_cost, 6630)
    assert.equal(economy.material_cost, 4075.75)

    const laborItem = economy.items.find(item => item.item_type === 'labor')
    const penetraceItem = economy.items.find(item => item.material_catalog_id === 'mat_penetrace')
    const smesItem = economy.items.find(item => item.material_catalog_id === 'mat_opravna_smes')

    assert.ok(laborItem)
    assert.ok(penetraceItem)
    assert.ok(smesItem)
    assert.equal(laborItem.quantity, 12.75)
    assert.equal(penetraceItem.quantity, 14.875)
    assert.equal(smesItem.quantity, 119)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testQuoteRecalculationPrefersManualArea() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const manualAreaResponse = await requestJson(port, '/api/projects/prj_1/analysis', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        referencePhotoId: 'pho_1',
        manualAreaSqm: 10,
        finalAreaSource: 'manual'
      })
    })

    assert.equal(manualAreaResponse.response.status, 200)

    const recalcResponse = await requestJson(port, '/api/projects/prj_1/quote-variants/recalculate', {
      method: 'POST'
    })

    assert.equal(recalcResponse.response.status, 200)

    const { response, body } = await requestJson(port, '/api/projects/prj_1/quote-variants')
    assert.equal(response.status, 200)

    const economy = body.items.find(item => item.variant_type === 'economy')
    assert.ok(economy)
    assert.equal(economy.labor_cost, 1560)
    assert.equal(economy.material_cost, 959)

    const laborItem = economy.items.find(item => item.item_type === 'labor')
    assert.ok(laborItem)
    assert.equal(laborItem.quantity, 3)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testProjectPatchEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/projects/prj_1', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        title: 'Fasada domu Novak - upraveno',
        description: 'Manualne upraveny popis projektu.',
        status: 'quoted',
        propertyType: 'facade',
        repairScope: 'full_reconstruction',
        addressLabel: 'Praha 8',
        locationLat: 50.104,
        locationLng: 14.47
      })
    })

    assert.equal(response.status, 200)
    assert.equal(body.title, 'Fasada domu Novak - upraveno')
    assert.equal(body.description, 'Manualne upraveny popis projektu.')
    assert.equal(body.status, 'quoted')
    assert.equal(body.repairScope, 'full_reconstruction')
    assert.equal(body.location.addressLabel, 'Praha 8')
    assert.equal(body.location.lat, 50.104)
    assert.equal(body.location.lng, 14.47)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testMaterialCatalogEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/material-catalog')

    assert.equal(response.status, 200)
    assert.ok(Array.isArray(body.items))
    assert.equal(body.items.length, 3)
    assert.equal(body.items[0].name, 'Fasadni nater')
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testSupplierPricesEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/material-catalog/mat_penetrace/supplier-prices')

    assert.equal(response.status, 200)
    assert.ok(Array.isArray(body.items))
    assert.equal(body.items.length, 2)
    assert.equal(body.items[0].supplier_name, 'DEK')
    assert.equal(body.items[0].unit_price, 79)
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testSuppliersEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/suppliers')

    assert.equal(response.status, 200)
    assert.ok(Array.isArray(body.items))
    assert.equal(body.items.length, 3)
    assert.deepEqual(
      body.items.map(item => item.name),
      ['DEK', 'Invest', 'Stavmat']
    )
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testSupplierPatchEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/suppliers/sup_dek', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name: 'DEK Partner Demo',
        websiteUrl: 'https://www.dek.cz',
        integrationType: 'partner_feed',
        contactName: 'Partnersky tym DEK',
        contactEmail: 'partneri@dek.cz'
      })
    })

    assert.equal(response.status, 200)
    assert.equal(body.id, 'sup_dek')
    assert.equal(body.name, 'DEK Partner Demo')
    assert.equal(body.website_url, 'https://www.dek.cz')
    assert.equal(body.integration_type, 'partner_feed')
    assert.equal(body.contact_name, 'Partnersky tym DEK')
    assert.equal(body.contact_email, 'partneri@dek.cz')
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function testMaterialCatalogPatchEndpoint() {
  bootstrapDatabase()
  const { server, port } = await startServer()

  try {
    const { response, body } = await requestJson(port, '/api/material-catalog/mat_penetrace', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        defaultUnitPrice: 95,
        defaultSupplierId: 'sup_stavmat',
        notes: 'Rucne potvrzena firemni cena.'
      })
    })

    assert.equal(response.status, 200)
    assert.equal(body.id, 'mat_penetrace')
    assert.equal(body.default_unit_price, 95)
    assert.equal(body.default_supplier_id, 'sup_stavmat')
    assert.equal(body.default_supplier_name, 'Stavmat')
    assert.equal(body.notes, 'Rucne potvrzena firemni cena.')
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function run() {
  const tests = [
    ['GET /api/projects vrati seeded projekty', testProjectsEndpoint],
    ['GET /api/projects/:id/analysis vrati seeded analyzu', testAnalysisEndpoint],
    ['POST /api/projects/:id/analysis pouzije nakonfigurovany AI provider', testAnalysisTriggerUsesConfiguredProvider],
    ['POST /api/projects/:id/analysis reaguje na metadata fotek', testAnalysisUsesPhotoMetadataAsInput],
    ['PATCH /api/projects/:id/analysis ulozi rucni oblast a plochu', testAnalysisManualAreaPatchEndpoint],
    ['GET /api/projects/:id/photos vrati minimum a vychozi fotku', testPhotosEndpointReturnsPrimaryAndMinimumMeta],
    ['POST /api/projects/:id/photos pripravi preview a ai_input varianty', testPhotoUploadCreatesPreviewAndAiInputVariants],
    ['POST /api/projects/:id/photos ulozi originalni soubor do local storage', testMultipartPhotoUploadStoresOriginalFileLocally],
    ['PATCH /api/projects/:id/photos/:photoId/primary prepne vychozi fotku', testSetPrimaryPhotoEndpoint],
    ['GET /api/projects/:id/quote-variants vrati tri cenove varianty', testQuoteVariantsEndpoint],
    ['POST /api/projects/:id/quote-variants/recalculate pocita podle plochy opravy', testQuoteRecalculationUsesAreaBasedPricing],
    ['POST /api/projects/:id/quote-variants/recalculate uprednostni rucni plochu', testQuoteRecalculationPrefersManualArea],
    ['PATCH /api/projects/:id ulozi zmeny projektu do SQLite', testProjectPatchEndpoint],
    ['GET /api/material-catalog vrati firemni katalog materialu', testMaterialCatalogEndpoint],
    ['GET /api/material-catalog/:id/supplier-prices vrati referencni ceny dodavatelu', testSupplierPricesEndpoint],
    ['GET /api/suppliers vrati aktivni dodavatele', testSuppliersEndpoint],
    ['PATCH /api/suppliers/:id ulozi zdroj dodavatele', testSupplierPatchEndpoint],
    ['PATCH /api/material-catalog/:id ulozi firemni cenu materialu', testMaterialCatalogPatchEndpoint]
  ]

  for (const [label, testFn] of tests) {
    await testFn()
    console.log(`PASS ${label}`)
  }
}

run().catch(error => {
  console.error(`FAIL ${error.message}`)
  console.error(error)
  process.exitCode = 1
})
