import { useState, useEffect } from 'react'

function App() {
  const [projects, setProjects] = useState([])
  const [name, setName] = useState('')
  const [area, setArea] = useState('')
  const [price, setPrice] = useState('')

  async function loadProjects() {
    try {
      const response = await fetch('http://localhost:3000/projects')
      if (!response.ok) throw new Error('Chyba serveru')
      const data = await response.json()
      setProjects(data)
    } catch (err) {
      alert('Nepodařilo se načíst projekty: ' + err.message)
    }
  }

  async function createProject() {
    if (!name || isNaN(area) || isNaN(price) || area <= 0 || price <= 0) {
      alert('Vyplňte prosím všechna pole správně.')
      return
    }

    try {
      const response = await fetch('http://localhost:3000/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, area: parseFloat(area), price: parseFloat(price) })
      })
      if (!response.ok) throw new Error('Chyba serveru')
      await loadProjects()
      setName('')
      setArea('')
      setPrice('')
    } catch (err) {
      alert('Nepodařilo se vytvořit projekt: ' + err.message)
    }
  }

  useEffect(() => {
    loadProjects()
  }, [])

  return (
    <div>
      <h1>Projekty</h1>

      <h2>Vytvořit projekt</h2>
      <input placeholder="název projektu" value={name} onChange={e => setName(e.target.value)} /><br /><br />
      <input placeholder="plocha m²" value={area} onChange={e => setArea(e.target.value)} /><br /><br />
      <input placeholder="cena" value={price} onChange={e => setPrice(e.target.value)} /><br /><br />
      <button onClick={createProject}>Vytvořit projekt</button>

      <ul>
        {projects.map(project => (
          <li key={project.id}>
            {project.name} - {project.area} m² - {project.price} Kč
          </li>
        ))}
      </ul>
    </div>
  )
}

export default App