// ==============================================================================
// MASTER JAVASCRIPT INITIALIZATION
// ==============================================================================
document.addEventListener('DOMContentLoaded', () => {
    // 1. Render Icons safely
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // 2. Initialize Global Features (Run on every page)
    initTheme();
    initSidebar();

    // 3. Initialize Page-Specific Features (Run ONLY if the page has these elements)
    if (document.getElementById('stepsRow')) {
        buildStepsRow(3, 10);
    }
    
    if (document.getElementById('timerDisplay')) {
        startCountdown(90);
    }
    
    if (document.querySelectorAll('.kit-section[id]').length > 0) {
        highlightNavOnScroll();
    }
});

// ==============================================================================
// 1. THEME TOGGLE LOGIC
// ==============================================================================
function initTheme() {
    const themeSwitch = document.getElementById('themeSwitch');
    const themeIcon   = document.getElementById('themeIcon');
    const themeLabel  = document.getElementById('themeLabel');

    const savedTheme = localStorage.getItem('psyche_theme') || 'dark';
    const isLightOnLoad = savedTheme === 'light';

    document.documentElement.setAttribute('data-theme', savedTheme);
    
    if (themeSwitch) {
        themeSwitch.checked = isLightOnLoad;
        if (themeIcon) themeIcon.setAttribute('data-lucide', isLightOnLoad ? 'moon' : 'sun');
        if (themeLabel) themeLabel.innerText = isLightOnLoad ? 'Light' : 'Dark';

        themeSwitch.addEventListener('change', () => {
            const isLight = themeSwitch.checked;
            const newTheme = isLight ? 'light' : 'dark';

            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('psyche_theme', newTheme);

            if (themeIcon) themeIcon.setAttribute('data-lucide', isLight ? 'moon' : 'sun');
            if (themeLabel) themeLabel.innerText = isLight ? 'Light' : 'Dark';
            
            if (typeof lucide !== 'undefined') lucide.createIcons();
        });
    }
}

// ==============================================================================
// 2. SIDEBAR COLLAPSE LOGIC
// ==============================================================================
function initSidebar() {
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarToggleIcon = document.getElementById('sidebarToggleIcon');
    const body = document.body;

    if (!sidebarToggle) return; // Exit if the button doesn't exist on this page

    // Check saved state
    const isSidebarCollapsed = localStorage.getItem('psyche_sidebar_collapsed') === 'true';

    // Apply state instantly
    if (isSidebarCollapsed) {
        body.classList.add('sidebar-collapsed');
        if (sidebarToggleIcon) sidebarToggleIcon.style.transform = 'rotate(180deg)';
    }

    // Toggle on click
    sidebarToggle.addEventListener('click', () => {
        const isNowCollapsed = body.classList.toggle('sidebar-collapsed');
        
        if (isNowCollapsed) {
            if (sidebarToggleIcon) sidebarToggleIcon.style.transform = 'rotate(180deg)';
        } else {
            if (sidebarToggleIcon) sidebarToggleIcon.style.transform = 'rotate(0deg)';
        }

        localStorage.setItem('psyche_sidebar_collapsed', isNowCollapsed);
    });
}

// ==============================================================================
// 3. COPY TO CLIPBOARD HELPER
// ==============================================================================
function copyToClipboard(text, el) {
    navigator.clipboard.writeText(`var(${text})`).catch(() => {});
    const box = el.querySelector('.swatch-box');
    if (box) { 
        box.style.outline = '2px solid var(--color-primary)'; 
        setTimeout(() => box.style.outline = '', 1200); 
    }
    const toast = document.getElementById('copyToast');
    if (toast) {
        toast.textContent = `Copied: var(${text})`;
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(-50%) translateY(0)';
        clearTimeout(copyToClipboard._tid);
        copyToClipboard._tid = setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(-50%) translateY(16px)';
        }, 2000);
    }
}

// ==============================================================================
// 4. QCM (MULTIPLE CHOICE) LOGIC
// ==============================================================================
let qcmRevealed = false;
const CORRECT_VALUES = ['b', 'd'];

function selectQCM(radio) {
    if (qcmRevealed) return;
}

function revealQCMAnswers() {
    const cards = document.querySelectorAll('.qcm-card');
    const note  = document.getElementById('qcmNote');
    if (!cards.length) return;

    if (qcmRevealed) {
        cards.forEach(c => { c.classList.remove('correct', 'wrong'); });
        document.querySelectorAll('.qcm-card input').forEach(i => i.checked = false);
        if (note) note.style.display = 'none';
        qcmRevealed = false;
        return;
    }

    cards.forEach(card => {
        const radio = card.querySelector('input[type="radio"]');
        if (radio) {
            const val = radio.value;
            card.classList.add(CORRECT_VALUES.includes(val) ? 'correct' : 'wrong');
        }
    });

    if (note) note.style.display = 'block';
    qcmRevealed = true;
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

// ==============================================================================
// 5. TEST PROGRESS BAR LOGIC
// ==============================================================================
let currentStep = 3;
const TOTAL_STEPS = 10;

function buildStepsRow(current, total) {
    const row = document.getElementById('stepsRow');
    const progressLabel = document.getElementById('progressLabel');
    const progressBar = document.getElementById('progressBar');
    
    if (!row || !progressBar) return;

    row.innerHTML = '';
    for (let i = 1; i <= total; i++) {
        const dot = document.createElement('div');
        dot.className = 'test-step-dot ' + (i < current ? 'done' : i === current ? 'current' : 'upcoming');
        row.appendChild(dot);
    }
    
    if (progressLabel) progressLabel.textContent = `Question ${current} of ${total}`;
    progressBar.style.width = `${((current - 1) / (total - 1)) * 100}%`;
}

function demoProgress(delta) {
    currentStep = Math.max(1, Math.min(TOTAL_STEPS, currentStep + delta));
    buildStepsRow(currentStep, TOTAL_STEPS);
}

// ==============================================================================
// 6. COUNTDOWN TIMER LOGIC
// ==============================================================================
let timerSeconds = 90;
let timerInterval = null;

function startCountdown(seconds) {
    timerSeconds = seconds;
    clearInterval(timerInterval);
    updateTimerDisplay();
    timerInterval = setInterval(() => {
        if (timerSeconds <= 0) { 
            clearInterval(timerInterval); 
            return; 
        }
        timerSeconds--;
        updateTimerDisplay();
    }, 1000);
}

function resetTimer() { 
    startCountdown(90); 
}

function updateTimerDisplay() {
    const badge   = document.getElementById('liveTimer');
    const display = document.getElementById('timerDisplay');
    
    if (!display) return;

    const mins = Math.floor(timerSeconds / 60);
    const secs = timerSeconds % 60;
    display.textContent = `${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')} remaining`;

    if (badge) {
        badge.className = 'countdown-badge';
        if (timerSeconds <= 15)      badge.classList.add('cb-critical');
        else if (timerSeconds <= 60) badge.classList.add('cb-warning');
        else                         badge.classList.add('cb-normal');
    }
}

// ==============================================================================
// 7. MODAL LOGIC
// ==============================================================================
function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('open');
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('open');
}

function handleModalOverlayClick(e, id) {
    if (e.target === document.getElementById(id)) closeModal(id);
}

// ==============================================================================
// 8. SCROLL-TRACKING NAVIGATION
// ==============================================================================
function highlightNavOnScroll() {
    const links    = document.querySelectorAll('.sidenav-link');
    const sections = Array.from(document.querySelectorAll('.kit-section[id]'));
    if (!links.length || !sections.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.id;
                links.forEach(l => {
                    // Only toggle if the link actually maps to a #id. 
                    // Protects our Django {% url %} links from being overwritten!
                    const href = l.getAttribute('href');
                    if (href && href.startsWith('#')) {
                        l.classList.toggle('active', href === `#${id}`);
                    }
                });
            }
        });
    }, { rootMargin: '-20% 0px -70% 0px' });

    sections.forEach(s => observer.observe(s));
}