export function WorkspaceHero() {
  return (
    <section className="workspace-hero" aria-labelledby="welcome-title">
      <div className="hero-copy">
        <p className="hero-eyebrow">A CV that feels like you</p>
        <h1 id="welcome-title">Your experience.<br /><em>A clearer story.</em></h1>
        <p className="hero-description">
          Bring your skills, projects and ambitions. Turn them into a thoughtful CV,
          tailored to the role you want next.
        </p>
        <a className="hero-cta" href="#profile-message">Start with your story <span aria-hidden="true">↗</span></a>
        <p className="hero-caption"><span aria-hidden="true">01 — 04</span> From a first introduction to your final PDF.</p>
      </div>
      <div className="hero-art" aria-hidden="true">
        <div className="paper-shadow" />
        <div className="preview-paper">
          <div className="paper-topline"><span>YOUR NEXT CHAPTER</span><span>CV / 01</span></div>
          <div className="paper-title">A little more<br /><i>you.</i></div>
          <div className="paper-rule" />
          <div className="paper-section"><span>01</span><div><strong>Experience</strong><div className="paper-line" /><div className="paper-line short" /></div></div>
          <div className="paper-section"><span>02</span><div><strong>Skills & strengths</strong><div className="paper-line" /><div className="paper-line medium" /></div></div>
          <div className="paper-section"><span>03</span><div><strong>Education & projects</strong><div className="paper-line" /><div className="paper-line short" /></div></div>
          <div className="paper-bottom">YOUR EXPERIENCE. YOUR WORDS. YOUR NEXT STEP.</div>
        </div>
        <div className="paper-label"><span className="paper-label-icon">↗</span><div>A considered first impression.<small>Shaped around your experience.</small></div></div>
      </div>
    </section>
  )
}
