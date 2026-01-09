/**
 * SIGINT Dashboard - Frontend Application
 */

// Configuration
const CONFIG = {
    // Will be replaced during deployment
    dataUrl: window.SIGINT_DATA_URL || '/data',
    refreshInterval: 60, // seconds
    categories: ['geopolitical', 'ai-ml', 'deep-tech', 'crypto-finance', 'narrative', 'breaking']
};

// State
let state = {
    lastUpdate: null,
    categories: {},
    narratives: [],
    countdown: CONFIG.refreshInterval,
    intervalId: null,
    countdownId: null
};

// DOM Elements
const elements = {
    statusDot: document.getElementById('statusDot'),
    statusText: document.getElementById('statusText'),
    lastUpdate: document.getElementById('lastUpdate'),
    breakingSection: document.getElementById('breakingSection'),
    breakingItems: document.getElementById('breakingItems'),
    refreshCountdown: document.getElementById('refreshCountdown'),
    refreshBtn: document.getElementById('refreshBtn'),
    archiveBtn: document.getElementById('archiveBtn'),
    archiveModal: document.getElementById('archiveModal'),
    archiveClose: document.getElementById('archiveClose'),
    archiveTabs: document.getElementById('archiveTabs'),
    archiveContent: document.getElementById('archiveContent')
};

// Utility Functions
function formatTime(date) {
    if (!date) return '--:--:--';
    const d = new Date(date);
    return d.toLocaleTimeString('en-US', { hour12: false });
}

function formatRelativeTime(date) {
    if (!date) return '';
    const now = new Date();
    const d = new Date(date);
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return d.toLocaleDateString();
}

function truncate(text, maxLength = 150) {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength).trim() + '...';
}

// API Functions
async function fetchDashboardData() {
    try {
        const response = await fetch(`${CONFIG.dataUrl}/current/dashboard.json?t=${Date.now()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
        throw error;
    }
}

async function fetchCategoryData(category) {
    try {
        const response = await fetch(`${CONFIG.dataUrl}/current/${category}.json?t=${Date.now()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`Failed to fetch ${category} data:`, error);
        return null;
    }
}

async function fetchArchiveData(category, date) {
    try {
        const response = await fetch(`${CONFIG.dataUrl}/archive/${date}/${category}.json?t=${Date.now()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`Failed to fetch archive for ${category}:`, error);
        return null;
    }
}

// Render Functions
function renderNewsItem(item, showSummary = true) {
    const urgencyClass = item.urgency ? `urgency-${item.urgency}` : '';
    const tags = item.tags || [];
    
    return `
        <article class="news-item ${urgencyClass}">
            <div class="news-item-header">
                <span class="news-item-source">${item.source || 'Unknown'}</span>
                <span class="news-item-time">${formatRelativeTime(item.published_at || item.fetched_at)}</span>
            </div>
            <h3 class="news-item-title">
                ${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>` : item.title}
            </h3>
            ${showSummary && item.summary ? `<p class="news-item-summary">${truncate(item.summary)}</p>` : ''}
            ${tags.length > 0 ? `
                <div class="news-item-tags">
                    ${tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
                </div>
            ` : ''}
        </article>
    `;
}

function renderNarrativeItem(item) {
    const strength = item.relevance_score || 0.5;
    const sources = item.tags || [];
    
    return `
        <article class="news-item">
            <div class="news-item-header">
                <span class="narrative-strength">
                    <div class="strength-bar">
                        <div class="strength-fill" style="width: ${strength * 100}%"></div>
                    </div>
                    ${Math.round(strength * 100)}%
                </span>
                <span class="news-item-time">${formatRelativeTime(item.fetched_at)}</span>
            </div>
            <h3 class="news-item-title">${item.title}</h3>
            <p class="news-item-summary">${item.summary}</p>
            ${sources.length > 0 ? `
                <div class="news-item-tags">
                    ${sources.map(s => `<span class="tag">${s}</span>`).join('')}
                </div>
            ` : ''}
        </article>
    `;
}

function renderBreakingItem(item) {
    return `
        <div class="breaking-item">
            <span class="breaking-item-time">${formatRelativeTime(item.published_at || item.fetched_at)}</span>
            <div class="breaking-item-text">
                <span class="breaking-item-title">
                    ${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>` : item.title}
                </span>
            </div>
        </div>
    `;
}

function renderPanel(category, data) {
    const panel = document.querySelector(`[data-category="${category}"]`);
    if (!panel) return;
    
    const itemsContainer = panel.querySelector('[data-items]');
    const updateSpan = panel.querySelector('[data-update]');
    
    if (!data || !data.items || data.items.length === 0) {
        itemsContainer.innerHTML = '<div class="empty-state">No data available</div>';
        return;
    }
    
    const isNarrative = category === 'narrative';
    itemsContainer.innerHTML = data.items
        .map(item => isNarrative ? renderNarrativeItem(item) : renderNewsItem(item))
        .join('');
    
    if (updateSpan && data.last_updated) {
        updateSpan.textContent = formatTime(data.last_updated);
    }
}

function renderBreaking(items) {
    if (!items || items.length === 0) {
        elements.breakingSection.style.display = 'none';
        return;
    }
    
    elements.breakingSection.style.display = 'block';
    elements.breakingItems.innerHTML = items.map(renderBreakingItem).join('');
}

function updateStatus(status, text) {
    elements.statusDot.className = `status-dot ${status}`;
    elements.statusText.textContent = text;
}

// Main Update Function
async function updateDashboard() {
    updateStatus('', 'UPDATING');
    
    try {
        // Try to fetch complete dashboard state first
        let dashboardData;
        try {
            dashboardData = await fetchDashboardData();
        } catch (e) {
            // Fall back to fetching individual categories
            dashboardData = null;
        }
        
        if (dashboardData && dashboardData.categories) {
            // Use dashboard data
            for (const [category, data] of Object.entries(dashboardData.categories)) {
                renderPanel(category, data);
            }
            
            // Render breaking news
            if (dashboardData.categories.breaking) {
                renderBreaking(dashboardData.categories.breaking.items);
            }
            
            state.lastUpdate = dashboardData.last_updated || new Date().toISOString();
        } else {
            // Fetch each category individually
            for (const category of CONFIG.categories) {
                if (category === 'breaking') continue; // Handle separately
                
                const data = await fetchCategoryData(category);
                if (data) {
                    renderPanel(category, data);
                }
            }
            
            // Fetch breaking news
            const breakingData = await fetchCategoryData('breaking');
            if (breakingData) {
                renderBreaking(breakingData.items);
            }
            
            state.lastUpdate = new Date().toISOString();
        }
        
        elements.lastUpdate.textContent = formatTime(state.lastUpdate);
        updateStatus('connected', 'LIVE');
        
    } catch (error) {
        console.error('Dashboard update failed:', error);
        updateStatus('error', 'ERROR');
    }
    
    // Reset countdown
    state.countdown = CONFIG.refreshInterval;
}

// Archive Modal
async function openArchive() {
    elements.archiveModal.style.display = 'flex';
    
    // Create tabs
    const categories = CONFIG.categories.filter(c => c !== 'breaking');
    elements.archiveTabs.innerHTML = categories.map((cat, i) => `
        <button class="archive-tab ${i === 0 ? 'active' : ''}" data-category="${cat}">
            ${cat.replace('-', '/').toUpperCase()}
        </button>
    `).join('');
    
    // Add tab click handlers
    elements.archiveTabs.querySelectorAll('.archive-tab').forEach(tab => {
        tab.addEventListener('click', () => loadArchiveCategory(tab.dataset.category));
    });
    
    // Load first category
    loadArchiveCategory(categories[0]);
}

async function loadArchiveCategory(category) {
    // Update active tab
    elements.archiveTabs.querySelectorAll('.archive-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.category === category);
    });
    
    elements.archiveContent.innerHTML = '<div class="loading">Loading archive</div>';
    
    const today = new Date().toISOString().split('T')[0];
    const data = await fetchArchiveData(category, today);
    
    if (!data || !data.items || data.items.length === 0) {
        elements.archiveContent.innerHTML = '<div class="empty-state">No archive data for today</div>';
        return;
    }
    
    elements.archiveContent.innerHTML = data.items.map(item => renderNewsItem(item)).join('');
}

function closeArchive() {
    elements.archiveModal.style.display = 'none';
}

// Countdown Timer
function updateCountdown() {
    state.countdown--;
    if (state.countdown <= 0) {
        state.countdown = CONFIG.refreshInterval;
        updateDashboard();
    }
    elements.refreshCountdown.textContent = state.countdown;
}

// Initialize
function init() {
    // Initial load
    updateDashboard();
    
    // Set up auto-refresh
    state.intervalId = setInterval(updateCountdown, 1000);
    
    // Event listeners
    elements.refreshBtn.addEventListener('click', () => {
        state.countdown = CONFIG.refreshInterval;
        updateDashboard();
    });
    
    elements.archiveBtn.addEventListener('click', openArchive);
    elements.archiveClose.addEventListener('click', closeArchive);
    elements.archiveModal.addEventListener('click', (e) => {
        if (e.target === elements.archiveModal) closeArchive();
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeArchive();
        if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            updateDashboard();
        }
    });
    
    console.log('[SIGINT] Dashboard initialized');
}

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
