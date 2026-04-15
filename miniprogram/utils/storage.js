/**
 * EasySpeak Storage Utilities
 * Wrapper around wx.storage with type safety, cache TTL, and key constants
 */

/* ========================================
   Storage Key Constants
   ======================================== */
var KEYS = {
  TOKEN: 'easyspeak_token',
  USER_INFO: 'easyspeak_user_info',
  DAILY_CACHE: 'easyspeak_daily_cache',
  DAILY_CACHE_TIME: 'easyspeak_daily_cache_time',
  CONTENT_CACHE_PREFIX: 'easyspeak_content_',
  REVIEW_CACHE: 'easyspeak_review_cache',
  QUIZ_HISTORY: 'easyspeak_quiz_history',
  SETTINGS: 'easyspeak_settings',
  DARK_MODE: 'easyspeak_dark_mode',
  STUDY_CALENDAR: 'easyspeak_study_calendar',
  LAST_STUDY_DATE: 'easyspeak_last_study_date',
  STREAK_DAYS: 'easyspeak_streak_days',
  WORD_MASTERY_CACHE: 'easyspeak_word_mastery_cache'
}

/* ========================================
   Cache TTL Constants (milliseconds)
   ======================================== */
var TTL = {
  DAILY_CONTENT: 24 * 60 * 60 * 1000,    // 24 hours
  CONTENT_DETAIL: 7 * 24 * 60 * 60 * 1000, // 7 days
  REVIEW_DATA: 30 * 60 * 1000,             // 30 minutes
  USER_PROGRESS: 10 * 60 * 1000,           // 10 minutes
  QUIZ_STATS: 60 * 60 * 1000               // 1 hour
}

/* ========================================
   Basic Storage Operations
   ======================================== */

/**
 * Get value from storage
 * @param {string} key - Storage key
 * @returns {*} Parsed value or null
 */
function get(key) {
  try {
    var value = wx.getStorageSync(key)
    if (value === '' || value === undefined || value === null) {
      return null
    }
    // Try to parse JSON
    if (typeof value === 'string') {
      try {
        return JSON.parse(value)
      } catch (e) {
        // Not JSON, return raw string
        return value
      }
    }
    return value
  } catch (e) {
    console.error('[Storage] get failed for key:', key, e)
    return null
  }
}

/**
 * Set value in storage
 * @param {string} key - Storage key
 * @param {*} value - Value to store (will be JSON serialized)
 */
function set(key, value) {
  try {
    if (typeof value === 'string') {
      wx.setStorageSync(key, value)
    } else {
      wx.setStorageSync(key, JSON.stringify(value))
    }
    return true
  } catch (e) {
    console.error('[Storage] set failed for key:', key, e)
    return false
  }
}

/**
 * Remove value from storage
 * @param {string} key - Storage key
 */
function remove(key) {
  try {
    wx.removeStorageSync(key)
    return true
  } catch (e) {
    console.error('[Storage] remove failed for key:', key, e)
    return false
  }
}

/**
 * Clear all EasySpeak-related storage (prefixed keys)
 */
function clearAll() {
  try {
    // Clear known keys
    var allKeys = Object.values(KEYS)
    allKeys.forEach(function(key) {
      wx.removeStorageSync(key)
    })

    // Also try to clear any cached content keys
    var info = wx.getStorageInfoSync()
    if (info && info.keys) {
      info.keys.forEach(function(key) {
        if (key.indexOf('easyspeak_') === 0) {
          wx.removeStorageSync(key)
        }
      })
    }

    console.log('[Storage] All EasySpeak data cleared')
    return true
  } catch (e) {
    console.error('[Storage] clearAll failed:', e)
    return false
  }
}

/* ========================================
   Cache with TTL Support
   ======================================== */

/**
 * Set a cached value with a timestamp for TTL checking
 * @param {string} key - Storage key
 * @param {*} value - Value to cache
 * @param {number} ttl - Time-to-live in milliseconds
 */
function setCache(key, value, ttl) {
  var cacheData = {
    value: value,
    timestamp: Date.now(),
    ttl: ttl
  }
  return set(key, cacheData)
}

/**
 * Get a cached value if it hasn't expired
 * @param {string} key - Storage key
 * @returns {*} Cached value or null if expired/missing
 */
function getCache(key) {
  var cacheData = get(key)
  if (!cacheData || !cacheData.timestamp) {
    return null
  }

  var now = Date.now()
  var elapsed = now - cacheData.timestamp

  if (elapsed > cacheData.ttl) {
    // Cache expired — remove it
    remove(key)
    return null
  }

  return cacheData.value
}

/**
 * Check if a cache entry exists and is valid
 * @param {string} key - Storage key
 * @returns {boolean}
 */
function hasValidCache(key) {
  return getCache(key) !== null
}

/**
 * Invalidate (remove) a cache entry
 * @param {string} key - Storage key
 */
function invalidateCache(key) {
  return remove(key)
}

/* ========================================
   Daily Content Cache Helpers
   ======================================== */

/**
 * Cache today's daily content
 * @param {string} date - Date string (YYYY-MM-DD)
 * @param {object} data - Daily content data
 */
function setDailyCache(date, data) {
  var cacheKey = KEYS.CONTENT_CACHE_PREFIX + date
  setCache(cacheKey, data, TTL.DAILY_CONTENT)
  // Also store the most recent daily cache
  setCache(KEYS.DAILY_CACHE, data, TTL.DAILY_CONTENT)
}

/**
 * Get cached daily content for a specific date
 * @param {string} date - Date string (YYYY-MM-DD)
 * @returns {object|null}
 */
function getDailyCache(date) {
  var cacheKey = KEYS.CONTENT_CACHE_PREFIX + date
  return getCache(cacheKey)
}

/**
 * Get today's cached content (shortcut)
 * @returns {object|null}
 */
function getTodayCache() {
  return getCache(KEYS.DAILY_CACHE)
}

/* ========================================
   Study Data Helpers
   ======================================== */

/**
 * Record a study day for streak tracking
 */
function recordStudyDay() {
  var today = formatDate(new Date())
  var lastDate = get(KEYS.LAST_STUDY_DATE)
  var streak = get(KEYS.STREAK_DAYS) || 0

  if (lastDate === today) {
    // Already recorded today, no change
    return
  }

  var yesterday = formatDate(new Date(Date.now() - 24 * 60 * 60 * 1000))
  if (lastDate === yesterday) {
    // Consecutive day — increment streak
    streak += 1
  } else {
    // Streak broken — reset to 1
    streak = 1
  }

  set(KEYS.LAST_STUDY_DATE, today)
  set(KEYS.STREAK_DAYS, streak)

  // Also update the calendar cache
  var calendar = get(KEYS.STUDY_CALENDAR) || []
  if (calendar.indexOf(today) === -1) {
    calendar.push(today)
    set(KEYS.STUDY_CALENDAR, calendar)
  }
}

/**
 * Get current study streak
 * @returns {number}
 */
function getStreakDays() {
  return get(KEYS.STREAK_DAYS) || 0
}

/**
 * Get study calendar (array of date strings)
 * @returns {string[]}
 */
function getStudyCalendar() {
  return get(KEYS.STUDY_CALENDAR) || []
}

/* ========================================
   Utility
   ======================================== */

/**
 * Format date to YYYY-MM-DD string
 * @param {Date} date
 * @returns {string}
 */
function formatDate(date) {
  var y = date.getFullYear()
  var m = String(date.getMonth() + 1).padStart(2, '0')
  var d = String(date.getDate()).padStart(2, '0')
  return y + '-' + m + '-' + d
}

/**
 * Get storage info (usage stats)
 * @returns {object}
 */
function getStorageInfo() {
  try {
    return wx.getStorageInfoSync()
  } catch (e) {
    return { keys: [], currentSize: 0, limitSize: 10240 }
  }
}

module.exports = {
  KEYS: KEYS,
  TTL: TTL,
  get: get,
  set: set,
  remove: remove,
  clearAll: clearAll,
  setCache: setCache,
  getCache: getCache,
  hasValidCache: hasValidCache,
  invalidateCache: invalidateCache,
  setDailyCache: setDailyCache,
  getDailyCache: getDailyCache,
  getTodayCache: getTodayCache,
  recordStudyDay: recordStudyDay,
  getStreakDays: getStreakDays,
  getStudyCalendar: getStudyCalendar,
  formatDate: formatDate,
  getStorageInfo: getStorageInfo
}
