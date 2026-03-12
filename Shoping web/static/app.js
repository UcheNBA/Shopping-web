// Theme toggle and small UI interactions
(function(){
  const body = document.body;
  const toggle = () => {
    const cur = localStorage.getItem('theme') || 'dark';
    const next = cur === 'dark' ? 'light' : 'dark';
    apply(next);
    localStorage.setItem('theme', next);
  };
  const apply = (theme) => {
    if(theme === 'light'){
      body.setAttribute('data-theme','light');
    } else {
      body.setAttribute('data-theme','dark');
    }
  };
  // add button handler
  document.addEventListener('DOMContentLoaded', ()=>{
    const btn = document.getElementById('theme-toggle');
    const saved = localStorage.getItem('theme') || 'dark';
    apply(saved);
    if(btn){ btn.addEventListener('click', toggle); }
    // fade-in cards
    document.querySelectorAll('.card').forEach((c,i)=>{
      c.style.opacity = 0;
      setTimeout(()=>{ c.classList.add('fade-in'); }, 80*i);
    });
  });
})();
