/**
 * SIGINT Dashboard - Frontend Application
 */

// Configuration
const CONFIG = {
    // Will be replaced during deployment
    dataUrl: 'https://d33bh3bu4kuavn.cloudfront.net/data',
    refreshInterval: 60, // seconds
    categories: ['geopolitical', 'ai-ml', 'deep-tech', 'crypto-finance', 'narrative', 'breaking', 'markets']
};

// State
let state = {
    lastUpdate: null,
    categories: {},
    narratives: [],
    countdown: CONFIG.refreshInterval,
    intervalId: null,
    countdownId: null,
    timeRangeHours: 24,  // Default to 24 hours
    archiveData: {}      // Cache for archive data by category
};

// Map instance
let sigintMap = null;

// DOM Elements
const elements = {
    statusDot: document.getElementById('statusDot'),
    statusText: document.getElementById('statusText'),
    lastUpdate: document.getElementById('lastUpdate'),
    breakingSection: document.getElementById('breakingSection'),
    breakingItems: document.getElementById('breakingItems'),
    tickerTrack: document.getElementById('tickerTrack'),
    refreshCountdown: document.getElementById('refreshCountdown'),
    refreshBtn: document.getElementById('refreshBtn'),
    archiveBtn: document.getElementById('archiveBtn'),
    archiveModal: document.getElementById('archiveModal'),
    archiveClose: document.getElementById('archiveClose'),
    archiveTabs: document.getElementById('archiveTabs'),
    archiveContent: document.getElementById('archiveContent'),
    archiveDateSelect: document.getElementById('archiveDateSelect'),
    exportJsonBtn: document.getElementById('exportJsonBtn'),
    exportCsvBtn: document.getElementById('exportCsvBtn'),
    timeRangeSlider: document.getElementById('timeRangeSlider'),
    timeRangeValue: document.getElementById('timeRangeValue')
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

async function fetchArchiveRange(category, days) {
    /**
     * Fetch archive data for a category over multiple days.
     * Returns merged items sorted by date, deduplicated by ID.
     */
    const items = [];
    const seenIds = new Set();
    
    for (let i = 0; i < days; i++) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        const dateStr = date.toISOString().split('T')[0];
        
        try {
            const data = await fetchArchiveData(category, dateStr);
            if (data && data.items) {
                for (const item of data.items) {
                    if (!seenIds.has(item.id)) {
                        seenIds.add(item.id);
                        items.push(item);
                    }
                }
            }
        } catch (error) {
            // Expected for missing days, continue
            console.debug(`No archive for ${category} on ${dateStr}`);
        }
    }
    
    // Sort by published date (newest first)
    items.sort((a, b) => {
        const dateA = new Date(a.published_at || a.fetched_at || 0);
        const dateB = new Date(b.published_at || b.fetched_at || 0);
        return dateB - dateA;
    });
    
    return items;
}

function formatTimeRangeLabel(hours) {
    /**
     * Convert hours to human-readable label.
     */
    if (hours <= 24) return '24 hours';
    if (hours <= 48) return '2 days';
    if (hours <= 72) return '3 days';
    if (hours <= 168) return '7 days';
    if (hours <= 336) return '14 days';
    if (hours <= 504) return '21 days';
    return '30 days';
}

async function filterItemsByAge(items, maxAgeHours) {
    /**
     * Filter items to only include those within maxAgeHours.
     */
    const cutoff = new Date();
    cutoff.setHours(cutoff.getHours() - maxAgeHours);
    
    return items.filter(item => {
        const itemDate = new Date(item.published_at || item.fetched_at);
        return itemDate >= cutoff;
    });
}

// Render Functions
function renderNewsItem(item, showSummary = true) {
    const urgencyClass = item.urgency ? `urgency-${item.urgency}` : '';
    const tags = item.tags || [];
    const pm = item.prediction_market;
    
    // Build prediction market badge if present
    let pmBadge = '';
    if (pm && pm.question) {
        const hasProb = pm.probability !== null && pm.probability !== undefined;
        const prob = hasProb ? Math.round(pm.probability * 100) : null;
        const probClass = hasProb ? (prob >= 70 ? 'pm-high' : prob >= 40 ? 'pm-medium' : 'pm-low') : 'pm-neutral';
        pmBadge = `
            <div class="prediction-market-badge ${probClass}">
                <div class="pm-header">
                    <span class="pm-icon">📊</span>
                    <span class="pm-source">${pm.source || 'Prediction'}</span>
                </div>
                <div class="pm-question">${truncate(pm.question, 80)}</div>
                <div class="pm-stats">
                    ${hasProb ? `<span class="pm-probability">${prob}%</span>` : '<span class="pm-probability">—</span>'}
                    ${pm.volume ? `<span class="pm-volume">${pm.volume}</span>` : ''}
                </div>
                ${pm.url ? `<a href="${pm.url}" target="_blank" rel="noopener" class="pm-link">View Market →</a>` : ''}
            </div>
        `;
    }
    
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
            ${pmBadge}
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

// Market Ticker Rendering
function renderTickerItem(item) {
    const title = item.title || '';
    // Parse: "Bitcoin: $100,000.00 (+5.5%)" or "Avalanche-2: $14.01 (+0.03%)"
    const match = title.match(/^([\w-]+):\s*\$?([\d,]+\.?\d*)\s*\(([+-]?[\d.]+)%\)/i);
    if (!match) return '';
    
    let name = match[1].toUpperCase().replace(/-\d+$/, ''); // Remove trailing "-2" etc
    const price = '$' + match[2];
    const change = parseFloat(match[3]);
    
    // Map to ticker symbols
    const symbols = {
        'BITCOIN': 'BTC', 'ETHEREUM': 'ETH', 'SOLANA': 'SOL',
        'DOGECOIN': 'DOGE', 'RIPPLE': 'XRP', 'CARDANO': 'ADA',
        'POLKADOT': 'DOT', 'AVALANCHE': 'AVAX', 'CHAINLINK': 'LINK',
        'POLYGON': 'MATIC', 'TETHER': 'USDT', 'BNB': 'BNB',
        'XRP': 'XRP', 'USD-COIN': 'USDC', 'STAKED-ETHER': 'STETH',
        'TRON': 'TRX', 'WRAPPED-BITCOIN': 'WBTC', 'THE-OPEN-NETWORK': 'TON',
        'SHIBA-INU': 'SHIB', 'LEO-TOKEN': 'LEO', 'LITECOIN': 'LTC',
        'HEDERA-HASHGRAPH': 'HBAR', 'UNISWAP': 'UNI', 'PEPE': 'PEPE'
    };
    const symbol = symbols[name] || name.slice(0, 4);
    const changeClass = change > 0 ? 'up' : change < 0 ? 'down' : 'neutral';
    const arrow = change > 0 ? '▲' : change < 0 ? '▼' : '';
    
    return `<div class="ticker-item">
        <span class="ticker-symbol">${symbol}</span>
        <span class="ticker-price">${price}</span>
        <span class="ticker-change ${changeClass}">${arrow} ${change > 0 ? '+' : ''}${change.toFixed(2)}%</span>
    </div>`;
}

function renderTicker(data) {
    if (!elements.tickerTrack) return;
    if (!data || !data.items || data.items.length === 0) {
        elements.tickerTrack.innerHTML = '<div class="ticker-empty">Loading market data...</div>';
        return;
    }
    // Render items twice for seamless infinite scroll
    const items = data.items.map(renderTickerItem).filter(Boolean).join('');
    elements.tickerTrack.innerHTML = items + items;
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
            // Use dashboard data - store in state for map
            state.categories = dashboardData.categories;
            for (const [category, data] of Object.entries(dashboardData.categories)) {
                if (category === 'markets') {
                    renderTicker(data);
                } else {
                    renderPanel(category, data);
                }
            }
            
            // Render breaking news
            if (dashboardData.categories.breaking) {
                renderBreaking(dashboardData.categories.breaking.items);
            }
            
            // Markets not in dashboard.json, fetch separately
            if (!dashboardData.categories.markets) {
                const marketsData = await fetchCategoryData('markets');
                if (marketsData) renderTicker(marketsData);
            }
            
            state.lastUpdate = dashboardData.last_updated || new Date().toISOString();
        } else {
            // Fetch each category individually
            state.categories = {};
            for (const category of CONFIG.categories) {
                if (category === 'breaking' || category === 'markets') continue;
                
                const data = await fetchCategoryData(category);
                if (data) {
                    state.categories[category] = data;
                    renderPanel(category, data);
                }
            }
            
            // Fetch breaking news
            const breakingData = await fetchCategoryData('breaking');
            if (breakingData) {
                renderBreaking(breakingData.items);
            }
            
            // Fetch markets
            const marketsData = await fetchCategoryData('markets');
            if (marketsData) renderTicker(marketsData);
            
            state.lastUpdate = new Date().toISOString();
        }
        
        elements.lastUpdate.textContent = formatTime(state.lastUpdate);
        updateStatus('connected', 'LIVE');
        
        // Update map markers with all category data
        if (sigintMap) {
            sigintMap.updateMarkers(state.categories);
        }
        
    } catch (error) {
        console.error('Dashboard update failed:', error);
        updateStatus('error', 'ERROR');
    }
    
    // Reset countdown
    state.countdown = CONFIG.refreshInterval;
}

// Archive Modal
let archiveState = {
    currentCategory: null,
    currentDate: null,
    availableDates: [],
    currentItems: []
};

async function fetchArchiveIndex() {
    try {
        const response = await fetch(`${CONFIG.dataUrl}/archive/index.json?t=${Date.now()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.debug('No archive index found, using date fallback');
        return null;
    }
}

function generateDateOptions(days = 30) {
    const dates = [];
    for (let i = 0; i < days; i++) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        dates.push(date.toISOString().split('T')[0]);
    }
    return dates;
}

async function openArchive() {
    elements.archiveModal.style.display = 'flex';
    
    // Populate date dropdown
    const index = await fetchArchiveIndex();
    archiveState.availableDates = index?.available_dates || generateDateOptions(30);
    
    elements.archiveDateSelect.innerHTML = archiveState.availableDates.map((date, i) => {
        const d = new Date(date + 'T12:00:00');
        const label = i === 0 ? `Today (${date})` : 
                      i === 1 ? `Yesterday (${date})` :
                      d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
        return `<option value="${date}">${label}</option>`;
    }).join('');
    
    archiveState.currentDate = archiveState.availableDates[0] || new Date().toISOString().split('T')[0];
    
    // Create tabs
    const categories = CONFIG.categories.filter(c => c !== 'breaking' && c !== 'markets');
    elements.archiveTabs.innerHTML = categories.map((cat, i) => `
        <button class="archive-tab ${i === 0 ? 'active' : ''}" data-category="${cat}">
            ${cat.replace('-', '/').toUpperCase()}
        </button>
    `).join('');
    
    // Add tab click handlers
    elements.archiveTabs.querySelectorAll('.archive-tab').forEach(tab => {
        tab.addEventListener('click', () => loadArchiveCategory(tab.dataset.category));
    });
    
    // Add date change handler
    elements.archiveDateSelect.addEventListener('change', (e) => {
        archiveState.currentDate = e.target.value;
        if (archiveState.currentCategory) {
            loadArchiveCategory(archiveState.currentCategory);
        }
    });
    
    // Add export handlers
    elements.exportJsonBtn.addEventListener('click', exportArchiveJson);
    elements.exportCsvBtn.addEventListener('click', exportArchiveCsv);
    
    // Load first category
    archiveState.currentCategory = categories[0];
    loadArchiveCategory(categories[0]);
}

async function loadArchiveCategory(category) {
    archiveState.currentCategory = category;
    
    // Update active tab
    elements.archiveTabs.querySelectorAll('.archive-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.category === category);
    });
    
    elements.archiveContent.innerHTML = '<div class="loading">Loading archive</div>';
    
    const date = archiveState.currentDate || new Date().toISOString().split('T')[0];
    const data = await fetchArchiveData(category, date);
    
    if (!data || !data.items || data.items.length === 0) {
        archiveState.currentItems = [];
        elements.archiveContent.innerHTML = `<div class="empty-state">No archive data for ${date}</div>`;
        return;
    }
    
    archiveState.currentItems = data.items;
    elements.archiveContent.innerHTML = data.items.map(item => renderNewsItem(item)).join('');
}

function exportArchiveJson() {
    if (!archiveState.currentItems || archiveState.currentItems.length === 0) {
        alert('No data to export');
        return;
    }
    
    const exportData = {
        category: archiveState.currentCategory,
        date: archiveState.currentDate,
        exported_at: new Date().toISOString(),
        item_count: archiveState.currentItems.length,
        items: archiveState.currentItems
    };
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sigint-${archiveState.currentCategory}-${archiveState.currentDate}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function exportArchiveCsv() {
    if (!archiveState.currentItems || archiveState.currentItems.length === 0) {
        alert('No data to export');
        return;
    }
    
    // CSV header
    const headers = ['id', 'title', 'summary', 'url', 'source', 'category', 'urgency', 'relevance_score', 'published_at'];
    const csvRows = [headers.join(',')];
    
    // CSV rows
    for (const item of archiveState.currentItems) {
        const row = [
            item.id || '',
            `"${(item.title || '').replace(/"/g, '""')}"`,
            `"${((item.summary || '').substring(0, 200)).replace(/"/g, '""')}"`,
            item.url || '',
            item.source || '',
            item.category || '',
            item.urgency || '',
            item.relevance_score || '',
            item.published_at || ''
        ];
        csvRows.push(row.join(','));
    }
    
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sigint-${archiveState.currentCategory}-${archiveState.currentDate}.csv`;
    a.click();
    URL.revokeObjectURL(url);
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

// Time Range Slider
async function handleTimeRangeChange(hours) {
    state.timeRangeHours = hours;
    
    // Update display
    if (elements.timeRangeValue) {
        elements.timeRangeValue.textContent = formatTimeRangeLabel(hours);
    }
    
    // Update active mark
    document.querySelectorAll('.time-range-marks span').forEach(mark => {
        const markValue = parseInt(mark.dataset.value);
        mark.classList.toggle('active', markValue === hours);
    });
    
    // If > 24 hours, fetch archive data and merge
    if (hours > 24) {
        updateStatus('loading', 'LOADING...');
        const days = Math.ceil(hours / 24);
        
        for (const category of CONFIG.categories) {
            if (category === 'breaking' || category === 'markets') continue;
            
            try {
                // Fetch current data
                const currentData = state.categories[category];
                if (!currentData) continue;
                
                // Fetch archive data for the range
                const archiveItems = await fetchArchiveRange(category, days);
                
                // Merge current with archive, deduplicate
                const seenIds = new Set();
                const mergedItems = [];
                
                // Add current items first
                for (const item of (currentData.items || [])) {
                    if (!seenIds.has(item.id)) {
                        seenIds.add(item.id);
                        mergedItems.push(item);
                    }
                }
                
                // Add archive items
                for (const item of archiveItems) {
                    if (!seenIds.has(item.id)) {
                        seenIds.add(item.id);
                        mergedItems.push(item);
                    }
                }
                
                // Filter by age and sort
                const filteredItems = await filterItemsByAge(mergedItems, hours);
                filteredItems.sort((a, b) => {
                    const dateA = new Date(a.published_at || a.fetched_at || 0);
                    const dateB = new Date(b.published_at || b.fetched_at || 0);
                    return dateB - dateA;
                });
                
                // Render merged data (limit to 15 items for display)
                const displayData = {
                    ...currentData,
                    items: filteredItems.slice(0, 15)
                };
                renderPanel(category, displayData);
                
            } catch (error) {
                console.error(`Error fetching archive for ${category}:`, error);
            }
        }
        
        updateStatus('connected', 'LIVE');
    } else {
        // Just show current data (re-render from state)
        for (const category of CONFIG.categories) {
            if (category === 'breaking' || category === 'markets') continue;
            const data = state.categories[category];
            if (data) {
                renderPanel(category, data);
            }
        }
    }
}

function initTimeRangeSlider() {
    if (!elements.timeRangeSlider) return;
    
    // Debounce for smooth sliding
    let debounceTimeout;
    
    elements.timeRangeSlider.addEventListener('input', (e) => {
        const hours = parseInt(e.target.value);
        
        // Update label immediately
        if (elements.timeRangeValue) {
            elements.timeRangeValue.textContent = formatTimeRangeLabel(hours);
        }
        
        // Debounce the actual data fetch
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
            handleTimeRangeChange(hours);
        }, 300);
    });
    
    // Click handlers for the marks
    document.querySelectorAll('.time-range-marks span').forEach(mark => {
        mark.addEventListener('click', () => {
            const value = parseInt(mark.dataset.value);
            elements.timeRangeSlider.value = value;
            handleTimeRangeChange(value);
        });
    });
    
    // Set initial active mark
    document.querySelector('.time-range-marks span[data-value="24"]')?.classList.add('active');
}

// Initialize
function init() {
    // Initialize the map
    if (window.SigintMap) {
        sigintMap = new window.SigintMap();
        sigintMap.init();
    }
    
    // Initialize time range slider
    initTimeRangeSlider();
    
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
