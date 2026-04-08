// ─────────────────────────────────────────────────────────────
    // INIT — Render Lucide icons
    // ─────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
      lucide.createIcons();
      buildStepsRow(3, 10);    // initialise progress bar: step 3 of 10
      startCountdown(90);      // start 90-second countdown
      highlightNavOnScroll();  // wire sidenav scroll tracking
    });

    // ─────────────────────────────────────────────────────────────
    // THEME TOGGLE
    // Reads the checkbox state and toggles data-theme on <html>.
    // ─────────────────────────────────────────────────────────────
    const themeSwitch = document.getElementById('themeSwitch');
    const themeIcon   = document.getElementById('themeIcon');

    themeSwitch.addEventListener('change', () => {
      const isLight = themeSwitch.checked;
      document.documentElement.setAttribute('data-theme', isLight ? 'light' : 'dark');
      // Swap the icon inside the toggle thumb
      themeIcon.setAttribute('data-lucide', isLight ? 'moon' : 'sun');
      lucide.createIcons();
    });

    // ─────────────────────────────────────────────────────────────
    // COPY TO CLIPBOARD — colour swatch helper
    // ─────────────────────────────────────────────────────────────
    function copyToClipboard(text, el) {
      navigator.clipboard.writeText(`var(${text})`).catch(() => {});
      // Visual feedback on the swatch
      const box = el.querySelector('.swatch-box');
      if (box) { box.style.outline = '2px solid var(--color-primary)'; setTimeout(() => box.style.outline = '', 1200); }
      // Show toast
      const toast = document.getElementById('copyToast');
      toast.textContent = `Copied: var(${text})`;
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(-50%) translateY(0)';
      clearTimeout(copyToClipboard._tid);
      copyToClipboard._tid = setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(-50%) translateY(16px)';
      }, 2000);
    }

    // ─────────────────────────────────────────────────────────────
    // QCM — ANSWER REVEAL
    // Applies .correct / .wrong classes to the label cards.
    // Correct answers: B (index 1) and D (index 3).
    // ─────────────────────────────────────────────────────────────
    let qcmRevealed = false;
    const CORRECT_VALUES = ['b', 'd'];

    function selectQCM(radio) {
      if (qcmRevealed) return; // lock during revealed state
    }

    function revealQCMAnswers() {
      const cards = document.querySelectorAll('.qcm-card');
      const note  = document.getElementById('qcmNote');

      if (qcmRevealed) {
        // Reset
        cards.forEach(c => { c.classList.remove('correct', 'wrong'); });
        document.querySelectorAll('.qcm-card input').forEach(i => i.checked = false);
        note.style.display = 'none';
        qcmRevealed = false;
        return;
      }

      cards.forEach(card => {
        const radio = card.querySelector('input[type="radio"]');
        const val   = radio.value;
        card.classList.add(CORRECT_VALUES.includes(val) ? 'correct' : 'wrong');
      });

      note.style.display = 'block';
      qcmRevealed = true;
      lucide.createIcons(); // re-render icons in the revealed state
    }

    // ─────────────────────────────────────────────────────────────
    // TEST PROGRESS BAR
    // ─────────────────────────────────────────────────────────────
    let currentStep = 3;
    const TOTAL_STEPS = 10;

    function buildStepsRow(current, total) {
      const row = document.getElementById('stepsRow');
      row.innerHTML = '';
      for (let i = 1; i <= total; i++) {
        const dot = document.createElement('div');
        dot.className = 'test-step-dot ' +
          (i < current ? 'done' : i === current ? 'current' : 'upcoming');
        row.appendChild(dot);
      }
      // Update label and bar width
      document.getElementById('progressLabel').textContent = `Question ${current} of ${total}`;
      document.getElementById('progressBar').style.width = `${((current - 1) / (total - 1)) * 100}%`;
    }

    function demoProgress(delta) {
      currentStep = Math.max(1, Math.min(TOTAL_STEPS, currentStep + delta));
      buildStepsRow(currentStep, TOTAL_STEPS);
    }

    // ─────────────────────────────────────────────────────────────
    // COUNTDOWN TIMER
    // ─────────────────────────────────────────────────────────────
    let timerSeconds = 90;
    let timerInterval = null;

    function startCountdown(seconds) {
      timerSeconds = seconds;
      clearInterval(timerInterval);
      updateTimerDisplay();
      timerInterval = setInterval(() => {
        if (timerSeconds <= 0) { clearInterval(timerInterval); return; }
        timerSeconds--;
        updateTimerDisplay();
      }, 1000);
    }

    function resetTimer() { startCountdown(90); }

    function updateTimerDisplay() {
      const badge   = document.getElementById('liveTimer');
      const display = document.getElementById('timerDisplay');
      const mins    = Math.floor(timerSeconds / 60);
      const secs    = timerSeconds % 60;
      display.textContent = `${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')} remaining`;

      // Swap class based on remaining time
      badge.className = 'countdown-badge';
      if (timerSeconds <= 15)     badge.classList.add('cb-critical');
      else if (timerSeconds <= 60) badge.classList.add('cb-warning');
      else                         badge.classList.add('cb-normal');
    }

    // ─────────────────────────────────────────────────────────────
    // RESULT MODALS
    // ─────────────────────────────────────────────────────────────
    function openModal(id) {
      document.getElementById(id).classList.add('open');
    }

    function closeModal(id) {
      document.getElementById(id).classList.remove('open');
    }

    function handleModalOverlayClick(e, id) {
      if (e.target === document.getElementById(id)) closeModal(id);
    }

    // ─────────────────────────────────────────────────────────────
    // SIDENAV — Scroll-tracking active state
    // ─────────────────────────────────────────────────────────────
    function highlightNavOnScroll() {
      const links    = document.querySelectorAll('.sidenav-link');
      const sections = Array.from(document.querySelectorAll('.kit-section[id]'));

      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const id = entry.target.id;
            links.forEach(l => {
              l.classList.toggle('active', l.getAttribute('href') === `#${id}`);
            });
          }
        });
      }, { rootMargin: '-20% 0px -70% 0px' });

      sections.forEach(s => observer.observe(s));
    }