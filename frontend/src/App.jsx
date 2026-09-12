import { useState } from 'react'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

function App() {
  const [file, setFile] = useState(null)
  const [paper, setPaper] = useState(null)
  const [status, setStatus] = useState('Ready for a paper')
  const [loading, setLoading] = useState(false)

  async function uploadPaper(event) {
    event.preventDefault()
    if (!file) return
    setLoading(true)
    setStatus('Reading paper...')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const response = await fetch(`${API_URL}/papers/upload`, { method: 'POST', body: formData })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || 'Upload failed')
      setPaper(result)
      setStatus('Analysis complete')
    } catch (error) {
      setStatus(error.message)
    } finally {
      setLoading(false)
    }
  }

  const sectionData = paper ? Object.entries(paper.sections).map(([name, value]) => ({ name: name.slice(0, 13), words: value.split(/\s+/).filter(Boolean).length })) : []
  const analysis = paper?.analysis

  return (
    <main>
      <header className="topbar"><div className="mark">LI</div><span>Literature Intelligence</span><span className="status"><i /> {status}</span></header>
      <section className="intro"><p className="eyebrow">ACADEMIC EVIDENCE DESK</p><h1>Turn a paper into a point of view.</h1><p className="lede">Upload one study to surface its structure, method, evidence, and open questions.</p></section>
      <form className="dropzone" onSubmit={uploadPaper}>
        <label htmlFor="paper-file"><span className="upload-icon">↑</span><strong>{file ? file.name : 'Choose an academic PDF'}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB selected` : 'PDF files up to 50 MB'}</small></label>
        <input id="paper-file" type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files[0])} />
        <button type="submit" disabled={!file || loading}>{loading ? 'Analysing...' : 'Analyse paper →'}</button>
      </form>
      {paper && <>
        <section className="paper-head"><div><p className="eyebrow">CURRENT PAPER · {paper.metadata.year || 'YEAR UNKNOWN'}</p><h2>{paper.metadata.title || paper.filename}</h2><p>{paper.metadata.authors.join(' · ') || 'Authors not detected'} {paper.metadata.doi && <span className="doi">DOI {paper.metadata.doi}</span>}</p></div><div className="score"><span>{analysis.evidence_score.score}</span><small>Evidence score<br />{analysis.evidence_score.label}</small></div></section>
        <section className="grid">
          <article className="panel chart-panel"><div className="panel-title"><h3>Section footprint</h3><span>{Object.keys(paper.sections).length} detected</span></div><ResponsiveContainer width="100%" height={220}><BarChart data={sectionData}><XAxis dataKey="name" tick={{ fill: '#68736d', fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis hide /><Tooltip cursor={{ fill: '#f2eee5' }} /><Bar dataKey="words" fill="#da5c3e" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></article>
          <article className="panel"><div className="panel-title"><h3>Methodology</h3><span>{analysis.methodology.available ? 'Found' : 'Not detected'}</span></div><p className="summary">{analysis.methodology.summary || 'No methodology section was detected.'}</p><div className="tags">{analysis.methodology.method_terms.map((term) => <span key={term}>{term}</span>)}</div></article>
          <article className="panel"><div className="panel-title"><h3>Claims</h3><span>{analysis.claims.length}</span></div><ul>{analysis.claims.slice(0, 4).map((claim) => <li key={claim}>{claim}</li>)}</ul></article>
          <article className="panel"><div className="panel-title"><h3>Research gaps</h3><span>{analysis.research_gaps.length}</span></div><ul>{analysis.research_gaps.slice(0, 4).map((gap) => <li key={gap}>{gap}</li>)}</ul></article>
          <article className="panel full"><div className="panel-title"><h3>Statistics found</h3><span>{analysis.statistics.length} signals</span></div><div className="stat-list">{analysis.statistics.slice(0, 6).map((stat) => <p key={stat}>{stat}</p>)}</div></article>
        </section>
      </>}
    </main>
  )
}

export default App
