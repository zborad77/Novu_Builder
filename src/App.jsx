import { useEffect, useRef, useState } from 'react'
import './App.css'

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1'
const MIN_PROJECT_PHOTOS = 3

const EMPTY_PROJECT_FORM = {
  title: '',
  description: '',
  addressLabel: '',
  repairScope: '',
  locationLat: '',
  locationLng: ''
}

const EMPTY_CREATE_FORM = {
  title: '',
  description: '',
  addressLabel: ''
}

const EMPTY_MATERIAL_FORM = {
  defaultUnitPrice: '',
  defaultSupplierId: '',
  notes: ''
}

const EMPTY_SUPPLIER_FORM = {
  name: '',
  websiteUrl: '',
  integrationType: 'manual',
  contactName: '',
  contactEmail: ''
}

const EMPTY_AREA_FORM = {
  referencePhotoId: '',
  manualAreaSqm: '',
  finalAreaSource: 'ai',
  selectedRepairPolygon: []
}

function formatCurrency(value) {
  if (typeof value !== 'number') {
    return 'N/A'
  }

  return new Intl.NumberFormat('cs-CZ', {
    style: 'currency',
    currency: 'CZK',
    maximumFractionDigits: 0
  }).format(value)
}

function formatArea(value) {
  if (typeof value !== 'number') {
    return 'N/A'
  }

  return `${value.toFixed(1)} m²`
}

function formatLabel(value) {
  if (!value) {
    return 'Nezadáno'
  }

  return value
}

function formatItemType(value) {
  switch (value) {
    case 'labor':
      return 'Práce'
    case 'material':
      return 'Materiál'
    case 'other':
      return 'Vedlejší náklady'
    default:
      return formatLabel(value)
  }
}

function normalizeProjectForm(detail) {
  if (!detail) {
    return EMPTY_PROJECT_FORM
  }

  return {
    title: detail.title ?? '',
    description: detail.description ?? '',
    addressLabel: detail.location?.addressLabel ?? '',
    repairScope: detail.repairScope ?? '',
    locationLat: detail.location?.lat ?? '',
    locationLng: detail.location?.lng ?? ''
  }
}

function normalizeMaterialForm(material) {
  if (!material) {
    return EMPTY_MATERIAL_FORM
  }

  return {
    defaultUnitPrice: material.default_unit_price ?? '',
    defaultSupplierId: material.default_supplier_id ?? '',
    notes: material.notes ?? ''
  }
}

function normalizeSupplierForm(supplier) {
  if (!supplier) {
    return EMPTY_SUPPLIER_FORM
  }

  return {
    name: supplier.name ?? '',
    websiteUrl: supplier.website_url ?? '',
    integrationType: supplier.integration_type ?? 'manual',
    contactName: supplier.contact_name ?? '',
    contactEmail: supplier.contact_email ?? ''
  }
}

function normalizeAreaForm(analysis) {
  if (!analysis) {
    return EMPTY_AREA_FORM
  }

  return {
    referencePhotoId: analysis.referencePhotoId ?? analysis.reference_photo_id ?? '',
    manualAreaSqm: analysis.manualAreaSqm ?? analysis.manual_area_sqm ?? '',
    finalAreaSource: analysis.finalAreaSource ?? analysis.final_area_source ?? 'ai',
    selectedRepairPolygon: Array.isArray(analysis.selectedRepairPolygon)
      ? analysis.selectedRepairPolygon
      : Array.isArray(analysis.selected_repair_polygon_json)
        ? analysis.selected_repair_polygon_json
      : []
  }
}

function clampNormalized(value) {
  return Math.min(1, Math.max(0, value))
}

function App() {
  const [projects, setProjects] = useState([])
  const [selectedProjectId, setSelectedProjectId] = useState(null)
  const [projectDetail, setProjectDetail] = useState(null)
  const [projectPhotos, setProjectPhotos] = useState([])
  const [projectAnalysis, setProjectAnalysis] = useState(null)
  const [quoteVariants, setQuoteVariants] = useState([])
  const [projectForm, setProjectForm] = useState(EMPTY_PROJECT_FORM)
  const [createForm, setCreateForm] = useState(EMPTY_CREATE_FORM)
  const [materialCatalog, setMaterialCatalog] = useState([])
  const [selectedMaterialId, setSelectedMaterialId] = useState(null)
  const [materialForm, setMaterialForm] = useState(EMPTY_MATERIAL_FORM)
  const [selectedSupplierId, setSelectedSupplierId] = useState(null)
  const [supplierForm, setSupplierForm] = useState(EMPTY_SUPPLIER_FORM)
  const [areaForm, setAreaForm] = useState(EMPTY_AREA_FORM)
  const [supplierPrices, setSupplierPrices] = useState([])
  const [suppliers, setSuppliers] = useState([])
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [loadingCatalog, setLoadingCatalog] = useState(true)
  const [loadingSupplierPrices, setLoadingSupplierPrices] = useState(false)
  const [savingProject, setSavingProject] = useState(false)
  const [creatingProject, setCreatingProject] = useState(false)
  const [savingMaterial, setSavingMaterial] = useState(false)
  const [savingSupplier, setSavingSupplier] = useState(false)
  const [savingArea, setSavingArea] = useState(false)
  const [runningAnalysis, setRunningAnalysis] = useState(false)
  const [recalculatingQuotes, setRecalculatingQuotes] = useState(false)
  const [projectsError, setProjectsError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [catalogError, setCatalogError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [workflowMessage, setWorkflowMessage] = useState('')
  const [catalogMessage, setCatalogMessage] = useState('')
  const [draggingPolygonPointIndex, setDraggingPolygonPointIndex] = useState(null)
  const polygonDragState = useRef({ moved: false })

  const selectedMaterial = materialCatalog.find(item => item.id === selectedMaterialId) ?? null
  const selectedSupplier = suppliers.find(item => item.id === selectedSupplierId) ?? null
  const primaryProjectPhoto = projectPhotos.find(photo => photo.isPrimary) ?? null
  const missingProjectPhotos = Math.max(MIN_PROJECT_PHOTOS - projectPhotos.length, 0)
  const hasEnoughProjectPhotos = missingProjectPhotos === 0
  const activeReferencePhoto = projectPhotos.find(photo => photo.id === areaForm.referencePhotoId) ?? primaryProjectPhoto ?? null

  async function fetchProjects() {
    const response = await fetch(`${API_BASE_URL}/cases`)
    if (!response.ok) {
      throw new Error('Nepodařilo se načíst projekty.')
    }

    const payload = await response.json()
    return payload.items ?? []
  }

  async function fetchMaterialCatalog() {
    const [materialsResponse, suppliersResponse] = await Promise.all([
      fetch(`${API_BASE_URL}/material-catalog`),
      fetch(`${API_BASE_URL}/suppliers`)
    ])

    if (!materialsResponse.ok) {
      throw new Error('Nepodařilo se načíst firemní katalog materiálů.')
    }

    const materialsPayload = await materialsResponse.json()
    const suppliersPayload = suppliersResponse.ok ? await suppliersResponse.json() : { items: [] }

    return {
      materials: materialsPayload.items ?? [],
      suppliers: suppliersPayload.items ?? []
    }
  }

  async function refreshProjects({ preserveSelection = true } = {}) {
    const items = await fetchProjects()
    setProjects(items)

    if (items.length === 0) {
      setSelectedProjectId(null)
      return items
    }

    if (!preserveSelection) {
      setSelectedProjectId(items[0].id)
      return items
    }

    setSelectedProjectId(currentId => {
      if (currentId && items.some(item => item.id === currentId)) {
        return currentId
      }

      return items[0].id
    })

    return items
  }

  async function refreshProjectWorkspace(projectId) {
    const [detailResponse, photosResponse, analysisResponse, quoteVariantsResponse] = await Promise.all([
      fetch(`${API_BASE_URL}/cases/${projectId}`),
      fetch(`${API_BASE_URL}/cases/${projectId}/images`),
      fetch(`${API_BASE_URL}/projects/${projectId}/analysis`),
      fetch(`${API_BASE_URL}/cases/${projectId}/estimates`)
    ])

    if (!detailResponse.ok) {
      throw new Error('Nepodařilo se načíst detail projektu.')
    }

    const detailPayload = await detailResponse.json()
    const photosPayload = photosResponse.ok ? await photosResponse.json() : { items: [] }
    const analysisPayload = analysisResponse.ok ? await analysisResponse.json() : null
    const quoteVariantsPayload = quoteVariantsResponse.ok ? await quoteVariantsResponse.json() : { items: [] }

    setProjectDetail(detailPayload)
    setProjectPhotos(photosPayload.items ?? [])
    setProjectAnalysis(analysisPayload)
    setQuoteVariants(quoteVariantsPayload.items ?? [])
    setProjectForm(normalizeProjectForm(detailPayload))
    setAreaForm(normalizeAreaForm(analysisPayload))
  }

  useEffect(() => {
    let active = true

    async function loadProjects() {
      setLoadingProjects(true)
      setProjectsError('')

      try {
        const items = await fetchProjects()
        if (!active) {
          return
        }

        setProjects(items)
        setSelectedProjectId(items.length > 0 ? items[0].id : null)
      } catch (error) {
        if (!active) {
          return
        }

        setProjectsError(error.message)
      } finally {
        if (active) {
          setLoadingProjects(false)
        }
      }
    }

    loadProjects()

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true

    async function loadCatalog() {
      setLoadingCatalog(true)
      setCatalogError('')

      try {
        const { materials, suppliers: supplierItems } = await fetchMaterialCatalog()
        if (!active) {
          return
        }

        setMaterialCatalog(materials)
        setSuppliers(supplierItems)
        setSelectedMaterialId(currentId => {
          if (currentId && materials.some(item => item.id === currentId)) {
            return currentId
          }

          return materials[0]?.id ?? null
        })
        setSelectedSupplierId(currentId => {
          if (currentId && supplierItems.some(item => item.id === currentId)) {
            return currentId
          }

          return supplierItems[0]?.id ?? null
        })
      } catch (error) {
        if (!active) {
          return
        }

        setCatalogError(error.message)
      } finally {
        if (active) {
          setLoadingCatalog(false)
        }
      }
    }

    loadCatalog()

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
      const material = materialCatalog.find(item => item.id === selectedMaterialId) ?? null
    setMaterialForm(normalizeMaterialForm(material))
  }, [selectedMaterialId, materialCatalog])

  useEffect(() => {
    const supplier = suppliers.find(item => item.id === selectedSupplierId) ?? null
    setSupplierForm(normalizeSupplierForm(supplier))
  }, [selectedSupplierId, suppliers])

  useEffect(() => {
    setAreaForm(normalizeAreaForm(projectAnalysis))
  }, [projectAnalysis])

  useEffect(() => {
    if (!suppliers.length) {
      setSelectedSupplierId(null)
      return
    }

    if (selectedMaterial?.default_supplier_id && suppliers.some(item => item.id === selectedMaterial.default_supplier_id)) {
      setSelectedSupplierId(selectedMaterial.default_supplier_id)
      return
    }

    setSelectedSupplierId(currentId => {
      if (currentId && suppliers.some(item => item.id === currentId)) {
        return currentId
      }

      return suppliers[0]?.id ?? null
    })
  }, [selectedMaterial?.default_supplier_id, suppliers])

  useEffect(() => {
    if (!selectedProjectId) {
      setProjectDetail(null)
      setProjectPhotos([])
      setProjectAnalysis(null)
      setQuoteVariants([])
      setProjectForm(EMPTY_PROJECT_FORM)
      return
    }

    let active = true

    async function loadProjectWorkspace() {
      setLoadingDetail(true)
      setDetailError('')
      setSaveMessage('')
      setWorkflowMessage('')

      try {
        await refreshProjectWorkspace(selectedProjectId)
        if (!active) {
          return
        }
      } catch (error) {
        if (!active) {
          return
        }

        setDetailError(error.message)
      } finally {
        if (active) {
          setLoadingDetail(false)
        }
      }
    }

    loadProjectWorkspace()

    return () => {
      active = false
    }
  }, [selectedProjectId])

  useEffect(() => {
    if (!selectedMaterialId) {
      setSupplierPrices([])
      return
    }

    let active = true

    async function loadSupplierPrices() {
      setLoadingSupplierPrices(true)
      setCatalogError('')

      try {
        const response = await fetch(`${API_BASE_URL}/material-catalog/${selectedMaterialId}/supplier-prices`)
        if (!response.ok) {
          throw new Error('Nepodařilo se načíst referenční ceny dodavatelů.')
        }

        const payload = await response.json()
        if (!active) {
          return
        }

        setSupplierPrices(payload.items ?? [])
      } catch (error) {
        if (!active) {
          return
        }

        setCatalogError(error.message)
      } finally {
        if (active) {
          setLoadingSupplierPrices(false)
        }
      }
    }

    loadSupplierPrices()

    return () => {
      active = false
    }
  }, [selectedMaterialId])

  function handleFormChange(event) {
    const { name, value } = event.target
    setProjectForm(current => ({
      ...current,
      [name]: value
    }))
  }

  function handleCreateFormChange(event) {
    const { name, value } = event.target
    setCreateForm(current => ({
      ...current,
      [name]: value
    }))
  }

  function handleMaterialFormChange(event) {
    const { name, value } = event.target
    setMaterialForm(current => ({
      ...current,
      [name]: value
    }))
  }

  function handleSupplierFormChange(event) {
    const { name, value } = event.target
    setSupplierForm(current => ({
      ...current,
      [name]: value
    }))
  }

  function handleAreaFormChange(event) {
    const { name, value } = event.target
    setAreaForm(current => ({
      ...current,
      [name]: value
    }))
  }

  function getNormalizedPointFromEvent(event) {
    const bounds = event.currentTarget.getBoundingClientRect()
    return {
      x: Number(clampNormalized((event.clientX - bounds.left) / bounds.width).toFixed(4)),
      y: Number(clampNormalized((event.clientY - bounds.top) / bounds.height).toFixed(4))
    }
  }

  function handlePolygonStageClick(event) {
    if (!activeReferencePhoto) {
      return
    }

    if (polygonDragState.current.moved) {
      polygonDragState.current.moved = false
      return
    }

    if (draggingPolygonPointIndex !== null) {
      return
    }

    const { x, y } = getNormalizedPointFromEvent(event)

    setAreaForm(current => ({
      ...current,
      referencePhotoId: current.referencePhotoId || activeReferencePhoto.id,
      selectedRepairPolygon: [
        ...(Array.isArray(current.selectedRepairPolygon) ? current.selectedRepairPolygon : []),
        { x, y }
      ]
    }))
  }

  function handlePolygonPointMouseDown(pointIndex, event) {
    event.preventDefault()
    event.stopPropagation()
    polygonDragState.current.moved = false
    setDraggingPolygonPointIndex(pointIndex)
  }

  function handlePolygonStageMouseMove(event) {
    if (draggingPolygonPointIndex === null) {
      return
    }

    const { x, y } = getNormalizedPointFromEvent(event)
    polygonDragState.current.moved = true

    setAreaForm(current => ({
      ...current,
      selectedRepairPolygon: (current.selectedRepairPolygon || []).map((point, index) =>
        index === draggingPolygonPointIndex ? { x, y } : point
      )
    }))
  }

  function handlePolygonStageMouseUp() {
    if (draggingPolygonPointIndex === null) {
      return
    }

    setDraggingPolygonPointIndex(null)
  }

  function handleRemoveLastPolygonPoint() {
    setAreaForm(current => ({
      ...current,
      selectedRepairPolygon: (current.selectedRepairPolygon || []).slice(0, -1)
    }))
  }

  function handleClearPolygon() {
    setAreaForm(current => ({
      ...current,
      selectedRepairPolygon: []
    }))
  }

  async function handleCreateProject(event) {
    event.preventDefault()

    if (!createForm.title.trim()) {
      setProjectsError('Nový projekt musí mít alespoň název.')
      return
    }

    setCreatingProject(true)
    setProjectsError('')
    setDetailError('')
    setSaveMessage('')
    setWorkflowMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/cases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: createForm.title.trim(),
          description: createForm.description.trim(),
          addressLabel: createForm.addressLabel.trim()
        })
      })

      if (!response.ok) {
        throw new Error('Nepodařilo se založit nový projekt.')
      }

      const payload = await response.json()
      await refreshProjects()
      setSelectedProjectId(payload.id)
      setCreateForm(EMPTY_CREATE_FORM)
      setWorkflowMessage('Nový projekt byl založen.')
    } catch (error) {
      setProjectsError(error.message)
    } finally {
      setCreatingProject(false)
    }
  }

  async function handleProjectSave(event) {
    event.preventDefault()

    if (!selectedProjectId) {
      return
    }

    setSavingProject(true)
    setDetailError('')
    setSaveMessage('')
    setWorkflowMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/cases/${selectedProjectId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: projectForm.title.trim(),
          description: projectForm.description.trim(),
          addressLabel: projectForm.addressLabel.trim(),
          repairScope: projectForm.repairScope.trim() || null,
          locationLat: projectForm.locationLat === '' ? null : Number(projectForm.locationLat),
          locationLng: projectForm.locationLng === '' ? null : Number(projectForm.locationLng)
        })
      })

      if (!response.ok) {
        throw new Error('Nepodařilo se uložit změny projektu.')
      }

      const updatedProject = await response.json()

      setProjectDetail(updatedProject)
      setProjectForm(normalizeProjectForm(updatedProject))
      setSaveMessage('Změny projektu byly uloženy.')
      await refreshProjects()
    } catch (error) {
      setDetailError(error.message)
    } finally {
      setSavingProject(false)
    }
  }

  async function handleMaterialSave(event) {
    event.preventDefault()

    if (!selectedMaterialId) {
      return
    }

    if (materialForm.defaultUnitPrice === '' || Number(materialForm.defaultUnitPrice) < 0) {
      setCatalogError('Firemni cena musi byt nezaporne cislo.')
      return
    }

    setSavingMaterial(true)
    setCatalogError('')
    setCatalogMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/material-catalog/${selectedMaterialId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          defaultUnitPrice: Number(materialForm.defaultUnitPrice),
          defaultSupplierId: materialForm.defaultSupplierId || null,
          notes: materialForm.notes
        })
      })

      if (!response.ok) {
        throw new Error('Nepodarilo se ulozit firemni cenu materialu.')
      }

      const updatedMaterial = await response.json()

      setMaterialCatalog(currentItems =>
        currentItems.map(item => (item.id === updatedMaterial.id ? updatedMaterial : item))
      )
      setMaterialForm(normalizeMaterialForm(updatedMaterial))
      setCatalogMessage('Firemni cena materialu byla ulozena.')
    } catch (error) {
      setCatalogError(error.message)
    } finally {
      setSavingMaterial(false)
    }
  }

  async function handleSupplierSave(event) {
    event.preventDefault()

    if (!selectedSupplierId) {
      return
    }

    if (!supplierForm.name.trim()) {
      setCatalogError('Dodavatel musi mit nazev.')
      return
    }

    setSavingSupplier(true)
    setCatalogError('')
    setCatalogMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/suppliers/${selectedSupplierId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: supplierForm.name.trim(),
          websiteUrl: supplierForm.websiteUrl.trim() || null,
          integrationType: supplierForm.integrationType,
          contactName: supplierForm.contactName.trim() || null,
          contactEmail: supplierForm.contactEmail.trim() || null
        })
      })

      if (!response.ok) {
        throw new Error('Nepodarilo se ulozit zdroj dodavatele.')
      }

      const updatedSupplier = await response.json()

      setSuppliers(currentItems =>
        currentItems.map(item => (item.id === updatedSupplier.id ? updatedSupplier : item))
      )
      setMaterialCatalog(currentItems =>
        currentItems.map(item =>
          item.default_supplier_id === updatedSupplier.id
            ? { ...item, default_supplier_name: updatedSupplier.name }
            : item
        )
      )
      setSupplierPrices(currentItems =>
        currentItems.map(item =>
          item.supplier_id === updatedSupplier.id
            ? { ...item, supplier_name: updatedSupplier.name }
            : item
        )
      )
      setSupplierForm(normalizeSupplierForm(updatedSupplier))
      setCatalogMessage('Zdroj dodavatele byl ulozen.')
    } catch (error) {
      setCatalogError(error.message)
    } finally {
      setSavingSupplier(false)
    }
  }

  async function handleAreaSave(event) {
    event.preventDefault()

    if (!selectedProjectId) {
      return
    }

    if (areaForm.finalAreaSource === 'manual') {
      const numericArea = Number(areaForm.manualAreaSqm)
      if (!Number.isFinite(numericArea) || numericArea <= 0) {
        setDetailError('Rucni plocha musi byt kladne cislo.')
        return
      }
    }

    setSavingArea(true)
    setDetailError('')
    setSaveMessage('')
    setWorkflowMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/cases/${selectedProjectId}/measurements`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          referenceImageId: areaForm.referencePhotoId || null,
          manualAreaSqm: areaForm.manualAreaSqm === '' ? null : Number(areaForm.manualAreaSqm),
          finalAreaSource: areaForm.finalAreaSource,
          selectedRepairPolygon: areaForm.selectedRepairPolygon
        })
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.error || 'Nepodarilo se ulozit rucni plochu opravy.')
      }

      const updatedAnalysis = await response.json()
      setProjectAnalysis(updatedAnalysis)
      setAreaForm(normalizeAreaForm(updatedAnalysis))
      setSaveMessage('Rucni plocha a referencni fotka byly ulozeny.')
    } catch (error) {
      setDetailError(error.message)
    } finally {
      setSavingArea(false)
    }
  }

  async function handleRunAnalysis() {
    if (!selectedProjectId) {
      return
    }

    setRunningAnalysis(true)
    setDetailError('')
    setSaveMessage('')
    setWorkflowMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/cases/${selectedProjectId}/analysis-jobs`, {
        method: 'POST'
      })

      if (!response.ok) {
        throw new Error('Nepodařilo se spustit analýzu.')
      }

      await refreshProjectWorkspace(selectedProjectId)
      await refreshProjects()
      setWorkflowMessage('Analýza byla spuštěna a nový výsledek je načtený.')
    } catch (error) {
      setDetailError(error.message)
    } finally {
      setRunningAnalysis(false)
    }
  }

  async function handleRecalculateVariants() {
    if (!selectedProjectId) {
      return
    }

    setRecalculatingQuotes(true)
    setDetailError('')
    setSaveMessage('')
    setWorkflowMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/cases/${selectedProjectId}/estimates/recalculate`, {
        method: 'POST'
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.error || 'Nepodařilo se přepočítat cenové varianty.')
      }

      await refreshProjectWorkspace(selectedProjectId)
      await refreshProjects()
      setWorkflowMessage('Cenové varianty byly přepočítány.')
    } catch (error) {
      setDetailError(error.message)
    } finally {
      setRecalculatingQuotes(false)
    }
  }

  async function handleSetPrimaryPhoto(photoId) {
    if (!selectedProjectId) {
      return
    }

    setDetailError('')
    setWorkflowMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/cases/${selectedProjectId}/images/${photoId}/primary`, {
        method: 'PATCH'
      })

      if (!response.ok) {
        throw new Error('Nepodařilo se nastavit výchozí fotku.')
      }

      await refreshProjectWorkspace(selectedProjectId)
      setWorkflowMessage('Výchozí fotka projektu byla nastavena.')
    } catch (error) {
      setDetailError(error.message)
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace-header">
        <div>
          <p className="eyebrow">FotoNabídka / Kancelář</p>
          <h1>Projekty připravené k nacenění</h1>
          <p className="hero-text">
            Tahle obrazovka už čte skutečná data z backendu a ukazuje základní tok:
            projekt, fotky, analýzu, cenové varianty i firemní ceník.
          </p>
        </div>

        <aside className="status-panel">
          <span className="panel-label">Aktuální backend stav</span>
          <ul>
            <li>Projects běží nad SQLite</li>
            <li>Photo metadata běží nad SQLite</li>
            <li>Analysis jobs a results běží nad SQLite</li>
            <li>Quote variants a items běží nad SQLite</li>
            <li>Material catalog a suppliers běží nad SQLite</li>
          </ul>
        </aside>
      </section>

      <section className="workspace-grid">
        <aside className="project-list-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Seznam projektů</p>
              <h2>Aktivní zakázky</h2>
            </div>
            <span className="pill">{projects.length}</span>
          </div>

          <section className="create-project-card">
            <div className="detail-card-header">
              <h3>Nový projekt</h3>
              <span className="pill">create</span>
            </div>

            <form className="compact-form" onSubmit={handleCreateProject}>
              <label className="field-group">
                <span className="field-label">Název</span>
                <input
                  name="title"
                  onChange={handleCreateFormChange}
                  type="text"
                  value={createForm.title}
                />
              </label>

              <label className="field-group">
                <span className="field-label">Adresa</span>
                <input
                  name="addressLabel"
                  onChange={handleCreateFormChange}
                  type="text"
                  value={createForm.addressLabel}
                />
              </label>

              <label className="field-group field-group-full">
                <span className="field-label">Popis</span>
                <textarea
                  name="description"
                  onChange={handleCreateFormChange}
                  rows="3"
                  value={createForm.description}
                />
              </label>

              <div className="form-actions field-group-full">
                <button className="primary-button" disabled={creatingProject} type="submit">
                  {creatingProject ? 'Zakládám...' : 'Založit projekt'}
                </button>
              </div>
            </form>
          </section>

          <section className="create-project-card">
            <div className="detail-card-header">
              <h3>Firemní ceník</h3>
              <span className="pill">{materialCatalog.length}</span>
            </div>

            {loadingCatalog ? <p className="helper-text">Načítám materiály...</p> : null}
            {catalogError ? <p className="error-text">{catalogError}</p> : null}
            {catalogMessage ? <p className="success-text">{catalogMessage}</p> : null}

            <div className="material-list">
              {materialCatalog.map(material => (
                <button
                  className={`material-list-item${material.id === selectedMaterialId ? ' is-active' : ''}`}
                  key={material.id}
                  onClick={() => {
                    setSelectedMaterialId(material.id)
                    setCatalogMessage('')
                  }}
                  type="button"
                >
                  <strong>{material.name}</strong>
                  <span>{formatCurrency(material.default_unit_price)} / {material.unit}</span>
                </button>
              ))}
            </div>
          </section>

          {loadingProjects ? <p className="helper-text">Načítám projekty...</p> : null}
          {projectsError ? <p className="error-text">{projectsError}</p> : null}

          <div className="project-list">
            {projects.map(project => (
              <button
                className={`project-list-item${project.id === selectedProjectId ? ' is-active' : ''}`}
                key={project.id}
                onClick={() => setSelectedProjectId(project.id)}
                type="button"
              >
                <span className="project-status">{project.status}</span>
                <strong>{project.title}</strong>
                <span>{formatLabel(project.addressLabel)}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="project-detail-panel">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Detail projektu</p>
              <h2>{projectDetail?.title ?? 'Vyber projekt'}</h2>
            </div>
            {projectDetail ? <span className="pill">{projectDetail.status}</span> : null}
          </div>

          {loadingDetail ? <p className="helper-text">Načítám detail projektu...</p> : null}
          {detailError ? <p className="error-text">{detailError}</p> : null}
          {saveMessage ? <p className="success-text">{saveMessage}</p> : null}
          {workflowMessage ? <p className="success-text">{workflowMessage}</p> : null}

          {!loadingDetail && !projectDetail ? (
            <p className="helper-text">Zatím tu není vybraný žádný projekt.</p>
          ) : null}

          {projectDetail ? (
            <div className="detail-stack">
              <section className="detail-card">
                <div className="detail-card-header">
                  <h3>Projektový workflow</h3>
                  <span className="pill">akce</span>
                </div>

                <div className="action-row">
                  <button
                    className="secondary-button"
                    disabled={runningAnalysis}
                    onClick={handleRunAnalysis}
                    type="button"
                  >
                    {runningAnalysis ? 'Spouštím analýzu...' : 'Spustit analýzu'}
                  </button>

                  <button
                    className="primary-button"
                    disabled={recalculatingQuotes}
                    onClick={handleRecalculateVariants}
                    type="button"
                  >
                    {recalculatingQuotes ? 'Přepočítávám...' : 'Přepočítat cenové varianty'}
                  </button>
                </div>
              </section>

              <section className="detail-card mobile-flow-card">
                <div className="detail-card-header">
                  <h3>Mobilni prototyp</h3>
                  <span className="pill">mobile</span>
                </div>

                <div className="mobile-flow-shell">
                  <div className="mobile-flow-screen">
                    <div className="mobile-flow-top">
                      <strong>Rychla korekce plochy</strong>
                      <span>{projectDetail.title}</span>
                    </div>

                    <form className="mobile-area-form" onSubmit={handleAreaSave}>
                      <label className="field-group">
                        <span className="field-label">Zdroj plochy</span>
                        <select
                          name="finalAreaSource"
                          onChange={handleAreaFormChange}
                          value={areaForm.finalAreaSource}
                        >
                          <option value="ai">AI odhad</option>
                          <option value="manual">Manualni plocha</option>
                        </select>
                      </label>

                      <label className="field-group">
                        <span className="field-label">Referencni fotka</span>
                        <select
                          name="referencePhotoId"
                          onChange={handleAreaFormChange}
                          value={areaForm.referencePhotoId}
                        >
                          <option value="">Vyber fotku</option>
                          {projectPhotos.map(photo => (
                            <option key={photo.id} value={photo.id}>
                              {photo.originalFilename}{photo.isPrimary ? ' (vychozi)' : ''}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="field-group">
                        <span className="field-label">Rucni plocha v m2</span>
                        <input
                          min="0"
                          name="manualAreaSqm"
                          onChange={handleAreaFormChange}
                          step="0.1"
                          type="number"
                          value={areaForm.manualAreaSqm}
                        />
                      </label>

                      <div className="mobile-summary-card">
                        <span>AI plocha: {formatArea(projectAnalysis?.estimated_area_sqm)}</span>
                        <span>Vychozi fotka: {formatLabel(primaryProjectPhoto?.originalFilename)}</span>
                      </div>

                      <button className="primary-button mobile-submit" disabled={savingArea} type="submit">
                        {savingArea ? 'Ukladam...' : 'Ulozit z mobilu'}
                      </button>
                    </form>
                  </div>
                </div>
              </section>

              <section className="detail-card">
                <div className="detail-card-header">
                  <h3>Základní informace</h3>
                  <span className="pill">editace</span>
                </div>

                <form className="project-edit-form" onSubmit={handleProjectSave}>
                  <label className="field-group">
                    <span className="field-label">Název projektu</span>
                    <input
                      name="title"
                      onChange={handleFormChange}
                      type="text"
                      value={projectForm.title}
                    />
                  </label>

                  <label className="field-group field-group-full">
                    <span className="field-label">Popis projektu</span>
                    <textarea
                      name="description"
                      onChange={handleFormChange}
                      rows="4"
                      value={projectForm.description}
                    />
                  </label>

                  <label className="field-group">
                    <span className="field-label">Adresa</span>
                    <input
                      name="addressLabel"
                      onChange={handleFormChange}
                      type="text"
                      value={projectForm.addressLabel}
                    />
                  </label>

                  <label className="field-group">
                    <span className="field-label">Rozsah opravy</span>
                    <select
                      name="repairScope"
                      onChange={handleFormChange}
                      value={projectForm.repairScope}
                    >
                      <option value="">Vyber rozsah</option>
                      <option value="cleaning">Čištění</option>
                      <option value="local_repair">Lokální oprava</option>
                      <option value="full_reconstruction">Kompletní rekonstrukce</option>
                    </select>
                  </label>

                  <label className="field-group">
                    <span className="field-label">GPS latitude</span>
                    <input
                      name="locationLat"
                      onChange={handleFormChange}
                      step="0.000001"
                      type="number"
                      value={projectForm.locationLat}
                    />
                  </label>

                  <label className="field-group">
                    <span className="field-label">GPS longitude</span>
                    <input
                      name="locationLng"
                      onChange={handleFormChange}
                      step="0.000001"
                      type="number"
                      value={projectForm.locationLng}
                    />
                  </label>

                  <div className="form-actions field-group-full">
                    <button className="primary-button" disabled={savingProject} type="submit">
                      {savingProject ? 'Ukládám...' : 'Uložit změny projektu'}
                    </button>
                  </div>
                </form>
              </section>

              <section className="detail-card">
                <h3>Souhrn projektu</h3>
                <div className="stats-grid">
                  <div>
                    <span className="stat-label">Adresa</span>
                    <strong>{formatLabel(projectDetail.location?.addressLabel)}</strong>
                  </div>
                  <div>
                    <span className="stat-label">Typ objektu</span>
                    <strong>{formatLabel(projectDetail.propertyType)}</strong>
                  </div>
                  <div>
                    <span className="stat-label">Rozsah opravy</span>
                    <strong>{formatLabel(projectDetail.repairScope)}</strong>
                  </div>
                  <div>
                    <span className="stat-label">Klient</span>
                    <strong>{formatLabel(projectDetail.client?.fullName)}</strong>
                  </div>
                </div>
                <p className="description-text">{formatLabel(projectDetail.description)}</p>
              </section>

              <section className="detail-card">
                <div className="detail-card-header">
                  <h3>Firemní ceník a reference dodavatelů</h3>
                  <span className="pill">{suppliers.length}</span>
                </div>

                {selectedMaterial ? (
                  <>
                    <div className="stats-grid catalog-summary-grid">
                      <div>
                        <span className="stat-label">Materiál</span>
                        <strong>{selectedMaterial.name}</strong>
                      </div>
                      <div>
                        <span className="stat-label">Firemní cena</span>
                        <strong>{formatCurrency(selectedMaterial.default_unit_price)} / {selectedMaterial.unit}</strong>
                      </div>
                      <div>
                        <span className="stat-label">Výchozí dodavatel</span>
                        <strong>{formatLabel(selectedMaterial.default_supplier_name)}</strong>
                      </div>
                      <div>
                        <span className="stat-label">Kategorie</span>
                        <strong>{formatLabel(selectedMaterial.category)}</strong>
                      </div>
                    </div>

                    <p className="description-text">{formatLabel(selectedMaterial.notes)}</p>

                    <form className="catalog-edit-form" onSubmit={handleMaterialSave}>
                      <label className="field-group">
                        <span className="field-label">Firemni cena</span>
                        <input
                          min="0"
                          name="defaultUnitPrice"
                          onChange={handleMaterialFormChange}
                          step="0.01"
                          type="number"
                          value={materialForm.defaultUnitPrice}
                        />
                      </label>

                      <label className="field-group">
                        <span className="field-label">Vychozi dodavatel</span>
                        <select
                          name="defaultSupplierId"
                          onChange={handleMaterialFormChange}
                          value={materialForm.defaultSupplierId}
                        >
                          <option value="">Bez vychoziho dodavatele</option>
                          {suppliers.map(supplier => (
                            <option key={supplier.id} value={supplier.id}>
                              {supplier.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="field-group field-group-full">
                        <span className="field-label">Interni poznamka</span>
                        <textarea
                          name="notes"
                          onChange={handleMaterialFormChange}
                          rows="3"
                          value={materialForm.notes}
                        />
                      </label>

                      <div className="form-actions field-group-full">
                        <button className="primary-button" disabled={savingMaterial} type="submit">
                          {savingMaterial ? 'Ukladam cenu...' : 'Ulozit firemni cenu'}
                        </button>
                      </div>
                    </form>

                    <div className="detail-card-header supplier-price-header">
                      <h3>Referenční ceny dodavatelů</h3>
                      <span className="pill">{supplierPrices.length}</span>
                    </div>

                    {loadingSupplierPrices ? <p className="helper-text">Načítám ceny dodavatelů...</p> : null}

                    <div className="supplier-price-grid">
                      {supplierPrices.map(price => (
                        <article className="supplier-price-card" key={price.id}>
                          <strong>{price.supplier_name}</strong>
                          <p>{formatCurrency(price.unit_price)} / {price.unit}</p>
                          <span>{formatLabel(price.availability_status)}</span>
                        </article>
                      ))}
                      {supplierPrices.length === 0 && !loadingSupplierPrices ? (
                        <p className="helper-text">K tomuto materiálu zatím nemáme referenční ceny.</p>
                      ) : null}
                    </div>

                    <div className="detail-card-header supplier-price-header">
                      <h3>Zdroj dodavatele pro demo integrace</h3>
                      <span className="pill">{selectedSupplier ? selectedSupplier.code ?? selectedSupplier.name : 'n/a'}</span>
                    </div>

                    <div className="supplier-management-shell">
                      <div className="supplier-selector-list">
                        {suppliers.map(supplier => (
                          <button
                            className={`supplier-selector-card${supplier.id === selectedSupplierId ? ' is-active' : ''}`}
                            key={supplier.id}
                            onClick={() => setSelectedSupplierId(supplier.id)}
                            type="button"
                          >
                            <strong>{supplier.name}</strong>
                            <span>{supplier.website_url || 'Bez URL zdroje'}</span>
                            <em>{supplier.integration_type || 'manual'}</em>
                          </button>
                        ))}
                      </div>

                      {selectedSupplier ? (
                        <form className="supplier-edit-form" onSubmit={handleSupplierSave}>
                          <div className="supplier-source-summary">
                            <strong>{selectedSupplier.name}</strong>
                            <span>
                              {selectedSupplier.website_url ? (
                                <a href={selectedSupplier.website_url} rel="noreferrer" target="_blank">
                                  {selectedSupplier.website_url}
                                </a>
                              ) : (
                                'Zdrojovy web zatim neni nastaven'
                              )}
                            </span>
                          </div>

                          <label className="field-group">
                            <span className="field-label">Nazev dodavatele</span>
                            <input
                              name="name"
                              onChange={handleSupplierFormChange}
                              type="text"
                              value={supplierForm.name}
                            />
                          </label>

                          <label className="field-group">
                            <span className="field-label">Web zdroje</span>
                            <input
                              name="websiteUrl"
                              onChange={handleSupplierFormChange}
                              placeholder="https://www.dek.cz"
                              type="url"
                              value={supplierForm.websiteUrl}
                            />
                          </label>

                          <label className="field-group">
                            <span className="field-label">Typ integrace</span>
                            <select
                              name="integrationType"
                              onChange={handleSupplierFormChange}
                              value={supplierForm.integrationType}
                            >
                              <option value="manual">manual</option>
                              <option value="csv_import">csv_import</option>
                              <option value="api">api</option>
                              <option value="partner_feed">partner_feed</option>
                            </select>
                          </label>

                          <label className="field-group">
                            <span className="field-label">Kontakt</span>
                            <input
                              name="contactName"
                              onChange={handleSupplierFormChange}
                              type="text"
                              value={supplierForm.contactName}
                            />
                          </label>

                          <label className="field-group">
                            <span className="field-label">Email</span>
                            <input
                              name="contactEmail"
                              onChange={handleSupplierFormChange}
                              type="email"
                              value={supplierForm.contactEmail}
                            />
                          </label>

                          <div className="form-actions field-group-full">
                            <button className="primary-button" disabled={savingSupplier} type="submit">
                              {savingSupplier ? 'Ukladam zdroj...' : 'Ulozit zdroj dodavatele'}
                            </button>
                          </div>
                        </form>
                      ) : (
                        <p className="helper-text">Vyber dodavatele pro upravu partner zdroje.</p>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="helper-text">Vyber materiál z levého panelu.</p>
                )}
              </section>

              <section className="detail-card">
                <div className="detail-card-header">
                  <h3>Fotky projektu</h3>
                  <span className="pill">{projectPhotos.length}</span>
                </div>
                <div className="photo-guidance">
                  <p className="helper-text">
                    Doporucene minimum jsou {MIN_PROJECT_PHOTOS} fotky a jedna z nich ma byt vychozi.
                  </p>
                  {!hasEnoughProjectPhotos ? (
                    <p className="warning-text">
                      Projektu chybi jeste {missingProjectPhotos} fotka/fotky do doporuceneho minima.
                    </p>
                  ) : null}
                  {primaryProjectPhoto ? (
                    <p className="success-text">Vychozi fotka: {primaryProjectPhoto.originalFilename}</p>
                  ) : (
                    <p className="warning-text">Projekt zatim nema nastavenou vychozi fotku.</p>
                  )}
                </div>
                <div className="tag-list">
                  {projectPhotos.map(photo => (
                    <div className={`tag-card${photo.isPrimary ? ' is-primary' : ''}`} key={photo.id}>
                      <div className="tag-card-header">
                        <strong>{photo.originalFilename}</strong>
                        {photo.isPrimary ? <span className="photo-primary-badge">Vychozi</span> : null}
                      </div>
                      <div className="tag-card-actions">
                        {!photo.isPrimary ? (
                          <button
                            className="secondary-button small-button"
                            onClick={() => handleSetPrimaryPhoto(photo.id)}
                            type="button"
                          >
                            Nastavit jako vychozi
                          </button>
                        ) : (
                          <span className="helper-inline">Hlavni referencni snimek projektu</span>
                        )}
                      </div>
                      <span>{photo.width && photo.height ? `${photo.width} × ${photo.height}` : 'Rozměry neznáme'}</span>
                    </div>
                  ))}
                  {projectPhotos.length === 0 ? <p className="helper-text">Projekt zatím nemá žádné fotky.</p> : null}
                </div>
              </section>

              <section className="detail-card">
                <div className="detail-card-header">
                  <h3>Poslední analýza</h3>
                  <span className="pill">{projectAnalysis ? 'hotovo' : 'chybí'}</span>
                </div>

{projectAnalysis ? (
                  <>
                    <div className="stats-grid">
                    <div>
                      <span className="stat-label">Objekt</span>
                      <strong>{formatLabel(projectAnalysis.objectType)}</strong>
                    </div>
                    <div>
                      <span className="stat-label">Doporučení</span>
                      <strong>{formatLabel(projectAnalysis.recommendedScope)}</strong>
                    </div>
                    <div>
                      <span className="stat-label">AI plocha</span>
                      <strong>{formatArea(projectAnalysis.estimatedAreaSqm)}</strong>
                    </div>
                    <div>
                      <span className="stat-label">Confidence</span>
                      <strong>{typeof projectAnalysis.areaConfidence === 'number' ? projectAnalysis.areaConfidence.toFixed(2) : 'N/A'}</strong>
                    </div>
                    <div>
                      <span className="stat-label">Finalni zdroj plochy</span>
                      <strong>{projectAnalysis.finalAreaSource === 'manual' ? 'Manual' : 'AI'}</strong>
                    </div>
                    <div>
                      <span className="stat-label">Manualni plocha</span>
                      <strong>{typeof projectAnalysis.manualAreaSqm === 'number' ? formatArea(projectAnalysis.manualAreaSqm) : 'N/A'}</strong>
                    </div>
                    <div>
                      <span className="stat-label">Referencni fotka</span>
                      <strong>{formatLabel(projectPhotos.find(photo => photo.id === projectAnalysis.referencePhotoId)?.originalFilename)}</strong>
                    </div>
                    <div>
                      <span className="stat-label">Model</span>
                      <strong>
                        {projectAnalysis.modelName
                          ? `${projectAnalysis.modelName} ${projectAnalysis.modelVersion ?? ''}`.trim()
                          : 'N/A'}
                      </strong>
                    </div>
                  </div>

                  <form className="analysis-edit-form" onSubmit={handleAreaSave}>
                    <label className="field-group">
                      <span className="field-label">Zdroj finalni plochy</span>
                      <select
                        name="finalAreaSource"
                        onChange={handleAreaFormChange}
                        value={areaForm.finalAreaSource}
                      >
                        <option value="ai">Pouzit AI odhad</option>
                        <option value="manual">Pouzit manualni plochu</option>
                      </select>
                    </label>

                    <label className="field-group">
                      <span className="field-label">Referencni fotka</span>
                      <select
                        name="referencePhotoId"
                        onChange={handleAreaFormChange}
                        value={areaForm.referencePhotoId}
                      >
                        <option value="">Bez referencni fotky</option>
                        {projectPhotos.map(photo => (
                          <option key={photo.id} value={photo.id}>
                            {photo.originalFilename}{photo.isPrimary ? ' (vychozi)' : ''}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="field-group">
                      <span className="field-label">Rucni plocha v m2</span>
                      <input
                        min="0"
                        name="manualAreaSqm"
                        onChange={handleAreaFormChange}
                        step="0.1"
                        type="number"
                        value={areaForm.manualAreaSqm}
                      />
                    </label>

                    <div className="field-group field-group-full">
                      <div className="polygon-editor-card">
                        <div className="polygon-editor-header">
                          <strong>Rucni oblast opravy</strong>
                          <span>{areaForm.selectedRepairPolygon.length} bodu</span>
                        </div>

                        {activeReferencePhoto ? (
                          <>
                            <div className="polygon-editor-meta">
                              <span>Fotka: {activeReferencePhoto.originalFilename}</span>
                              <span>
                                {activeReferencePhoto.width && activeReferencePhoto.height
                                  ? `${activeReferencePhoto.width} × ${activeReferencePhoto.height}`
                                  : 'Rozmery neznama'}
                              </span>
                            </div>

                            <button
                              className={`polygon-stage${draggingPolygonPointIndex !== null ? ' is-dragging' : ''}`}
                              onClick={handlePolygonStageClick}
                              onMouseLeave={handlePolygonStageMouseUp}
                              onMouseMove={handlePolygonStageMouseMove}
                              onMouseUp={handlePolygonStageMouseUp}
                              type="button"
                            >
                              <svg className="polygon-stage-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
                                {areaForm.selectedRepairPolygon.length >= 2 ? (
                                  <polyline
                                    fill={areaForm.selectedRepairPolygon.length >= 3 ? 'rgba(196, 98, 45, 0.18)' : 'none'}
                                    points={areaForm.selectedRepairPolygon.map(point => `${point.x * 100},${point.y * 100}`).join(' ')}
                                    stroke="#c4622d"
                                    strokeWidth="1.6"
                                  />
                                ) : null}
                                {areaForm.selectedRepairPolygon.map((point, index) => (
                                  <circle
                                    cx={point.x * 100}
                                    cy={point.y * 100}
                                    fill="#dd7736"
                                    key={`${point.x}-${point.y}-${index}`}
                                    r="1.8"
                                    stroke={draggingPolygonPointIndex === index ? '#8e4316' : '#ffffff'}
                                    strokeWidth="0.7"
                                    onMouseDown={event => handlePolygonPointMouseDown(index, event)}
                                  />
                                ))}
                              </svg>

                              <div className="polygon-stage-copy">
                                <strong>{activeReferencePhoto.originalFilename}</strong>
                                <span>Klikanim pridej body oblasti opravy</span>
                              </div>
                            </button>

                            <div className="polygon-actions">
                              <button
                                className="secondary-button small-button"
                                disabled={areaForm.selectedRepairPolygon.length === 0}
                                onClick={handleRemoveLastPolygonPoint}
                                type="button"
                              >
                                Odebrat posledni bod
                              </button>
                              <button
                                className="secondary-button small-button"
                                disabled={areaForm.selectedRepairPolygon.length === 0}
                                onClick={handleClearPolygon}
                                type="button"
                              >
                                Vymazat polygon
                              </button>
                            </div>
                          </>
                        ) : (
                          <p className="helper-text">Nejdriv vyber referencni fotku.</p>
                        )}

                        <p className="helper-text">
                          V dalsim kroku nad timhle zakladem doplnime presun bodu a mobilni verzi.
                        </p>
                      </div>
                    </div>

                    <div className="form-actions field-group-full">
                      <button className="primary-button" disabled={savingArea} type="submit">
                        {savingArea ? 'Ukladam plochu...' : 'Ulozit finalni plochu'}
                      </button>
                    </div>
                  </form>
                  </>
                ) : (
                  <p className="helper-text">Projekt zatím nemá žádný výsledek analýzy.</p>
                )}
              </section>

              <section className="detail-card">
                <div className="detail-card-header">
                  <h3>Cenové varianty</h3>
                  <span className="pill">{quoteVariants.length}</span>
                </div>

                <div className="variant-grid">
                  {quoteVariants.map(variant => (
                    <article className="variant-card" key={variant.id}>
                      <span className="card-badge">{variant.variantType}</span>
                      <h4>{formatCurrency(variant.totalIncVat)}</h4>
                      <p>Práce: {formatCurrency(variant.laborCost)}</p>
                      <p>Materiál: {formatCurrency(variant.materialCost)}</p>
                      <p>Marže: {typeof variant.marginPct === 'number' ? `${variant.marginPct}%` : 'N/A'}</p>

                      <div className="variant-items">
                        <div className="variant-items-header">
                          <strong>Položky varianty</strong>
                          <span>{variant.items?.length ?? 0}</span>
                        </div>

                        {variant.items?.map(item => (
                          <div className="variant-item-row" key={item.id}>
                            <div className="variant-item-topline">
                              <strong>{item.name}</strong>
                              <span>{formatCurrency(item.totalPrice)}</span>
                            </div>

                            <div className="variant-item-meta">
                              <span>{formatItemType(item.itemType)}</span>
                              <span>
                                {typeof item.quantity === 'number' ? item.quantity : 'N/A'} {item.unit ?? ''}
                              </span>
                              <span>{formatCurrency(item.unitPrice)} / {item.unit ?? 'jedn.'}</span>
                            </div>

                            {item.description ? (
                              <p className="variant-item-description">{item.description}</p>
                            ) : null}
                          </div>
                        ))}

                        {!variant.items?.length ? (
                          <p className="helper-text">Tato varianta zatím nemá položkový rozpad.</p>
                        ) : null}
                      </div>
                    </article>
                  ))}
                  {quoteVariants.length === 0 ? <p className="helper-text">Projekt zatím nemá cenové varianty.</p> : null}
                </div>
              </section>
            </div>
          ) : null}
        </section>
      </section>
    </main>
  )
}

export default App
