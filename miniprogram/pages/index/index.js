/**
 * EasySpeak - Index Page (首页)
 * Displays today's push content, phrases, words, progress, and review reminder.
 */

const api = require('../../utils/api')
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')

// Date helpers
const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function formatDateStr(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return y + '-' + m + '-' + d
}

function formatDisplayDate(dateStr) {
  const parts = dateStr.split('-')
  return parseInt(parts[1]) + '月' + parseInt(parts[2]) + '日'
}

function getWeekday(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return WEEKDAYS[d.getDay()]
}

Page({
  data: {
    // Loading states
    loading: true,
    refreshing: false,

    // Date picker
    currentDate: formatDateStr(new Date()),
    currentDateDisplay: '',
    currentWeekday: '',
    timeSlot: 'morning', // 'morning' | 'evening'

    // Today's content
    content: null,
    morningContent: null,
    eveningContent: null,

    // Phrases list
    phrases: [],

    // Words list
    words: [],

    // Progress
    phraseProgress: { current: 0, total: 5 },
    wordProgress: { current: 0, total: 20 },

    // Review
    reviewDueCount: 0,

    // Empty state
    isEmpty: false,

    // Error state
    error: false,
    errorMsg: ''
  },

  onLoad: function () {
    this._initDate()
  },

  onShow: function () {
    this._loadTodayData()
  },

  onPullDownRefresh: function () {
    this.setData({ refreshing: true })
    this._loadTodayData(true).then(function () {
      wx.stopPullDownRefresh()
    }).catch(function () {
      wx.stopPullDownRefresh()
    })
  },

  onShareAppMessage: function () {
    var slot = this.data.timeSlot === 'morning' ? '晨间' : '晚间'
    var theme = ''
    if (this.data.content) {
      theme = this.data.content.theme_zh || ''
    }
    return {
      title: 'EasySpeak · ' + slot + '推送 - ' + theme,
      path: '/pages/index/index'
    }
  },

  // ========================
  // Private Methods
  // ========================

  _initDate: function () {
    var now = new Date()
    var dateStr = formatDateStr(now)
    this.setData({
      currentDate: dateStr,
      currentDateDisplay: formatDisplayDate(dateStr),
      currentWeekday: getWeekday(dateStr)
    })
  },

  _loadTodayData: function (forceRefresh) {
    var self = this
    var dateStr = this.data.currentDate

    // Try cache first (unless force refresh)
    if (!forceRefresh) {
      var cached = storage.getDailyCache(dateStr)
      if (cached) {
        console.log('[Index] Using cached data for', dateStr)
        self._processData(cached)
        self.setData({ loading: false })
        // Still fetch in background to refresh cache
        self._fetchFromServer(dateStr)
        return Promise.resolve()
      }
    }

    return self._fetchFromServer(dateStr)
  },

  _fetchFromServer: function (dateStr) {
    var self = this
    self.setData({ loading: true, error: false, isEmpty: false })

    return auth.ensureLogin().then(function (loggedIn) {
      if (!loggedIn) {
        // Still allow viewing without login for content
        console.log('[Index] Login failed, fetching without auth')
      }
      return api.get('/daily/today', { date: dateStr })
    }).then(function (data) {
      console.log('[Index] API response:', data)
      // Cache the result
      storage.setDailyCache(dateStr, data)
      self._processData(data)
      self.setData({ loading: false, refreshing: false })
    }).catch(function (err) {
      console.error('[Index] Fetch failed:', err)
      self.setData({
        loading: false,
        refreshing: false,
        error: true,
        errorMsg: err.message || '加载失败'
      })
      // If we had cached data before, still show it
      var cached = storage.getDailyCache(dateStr)
      if (cached) {
        self._processData(cached)
        self.setData({ error: false })
      }
    })
  },

  _processData: function (data) {
    if (!data) {
      this.setData({ isEmpty: true, content: null, phrases: [], words: [] })
      return
    }

    // API returns { morning: {...}, evening: {...}, progress: {...}, review: {...} }
    var morning = data.morning || null
    var evening = data.evening || null

    this.setData({
      morningContent: morning,
      eveningContent: evening
    })

    // Set active content based on current timeSlot
    this._updateActiveContent()

    // Progress
    var progress = data.progress || {}
    this.setData({
      phraseProgress: {
        current: progress.phrases_learned || 0,
        total: progress.phrases_total || 5
      },
      wordProgress: {
        current: progress.words_learned || 0,
        total: progress.words_total || 20
      }
    })

    // Review
    var review = data.review || {}
    this.setData({
      reviewDueCount: review.due_count || 0
    })
  },

  _updateActiveContent: function () {
    var slot = this.data.timeSlot
    var content = slot === 'morning' ? this.data.morningContent : this.data.eveningContent

    if (!content) {
      this.setData({
        content: null,
        isEmpty: true,
        phrases: [],
        words: []
      })
      return
    }

    var phrases = (content.phrases || []).map(function (p) {
      return {
        id: p.id,
        phrase: p.phrase || '',
        explanation: p.explanation || '',
        examples: [
          { en: p.example_1 || '', cn: p.example_1_cn || '' },
          { en: p.example_2 || '', cn: p.example_2_cn || '' },
          { en: p.example_3 || '', cn: p.example_3_cn || '' }
        ].filter(function (e) { return e.en }),
        source: p.source || ''
      }
    })

    var words = (content.words || []).map(function (w) {
      return {
        id: w.id,
        word: w.word || '',
        phonetic: w.phonetic || '',
        partOfSpeech: w.part_of_speech || '',
        meaning: w.meaning || '',
        example: w.example || ''
      }
    })

    this.setData({
      content: content,
      isEmpty: false,
      phrases: phrases,
      words: words
    })
  },

  // ========================
  // Event Handlers
  // ========================

  onTimeSlotChange: function (e) {
    var slot = e.currentTarget.dataset.slot
    if (slot === this.data.timeSlot) return
    this.setData({ timeSlot: slot })
    this._updateActiveContent()
  },

  onPrevDate: function () {
    var current = new Date(this.data.currentDate + 'T00:00:00')
    current.setDate(current.getDate() - 1)
    var newDateStr = formatDateStr(current)
    this.setData({
      currentDate: newDateStr,
      currentDateDisplay: formatDisplayDate(newDateStr),
      currentWeekday: getWeekday(newDateStr)
    })
    this._loadTodayData()
  },

  onNextDate: function () {
    var today = formatDateStr(new Date())
    if (this.data.currentDate >= today) {
      wx.showToast({ title: '不能查看未来的内容哦', icon: 'none' })
      return
    }
    var current = new Date(this.data.currentDate + 'T00:00:00')
    current.setDate(current.getDate() + 1)
    var newDateStr = formatDateStr(current)
    this.setData({
      currentDate: newDateStr,
      currentDateDisplay: formatDisplayDate(newDateStr),
      currentWeekday: getWeekday(newDateStr)
    })
    this._loadTodayData()
  },

  onBackToToday: function () {
    var today = formatDateStr(new Date())
    if (this.data.currentDate === today) return
    this.setData({
      currentDate: today,
      currentDateDisplay: formatDisplayDate(today),
      currentWeekday: getWeekday(today)
    })
    this._loadTodayData()
  },

  onViewDetail: function () {
    var content = this.data.content
    if (!content || !content.id) return
    wx.navigateTo({
      url: '/pages/detail/detail?id=' + content.id
    })
  },

  onPhraseToggle: function (e) {
    // Phrase card expanded/collapsed — handled by component internally
  },

  onPhraseTap: function (e) {
    var id = e.currentTarget.dataset.id
    if (id) {
      wx.navigateTo({
        url: '/pages/detail/detail?phraseId=' + id
      })
    }
  },

  onViewAllPhrases: function () {
    var content = this.data.content
    if (!content || !content.id) return
    wx.navigateTo({
      url: '/pages/detail/detail?id=' + content.id + '&tab=phrases'
    })
  },

  onViewAllWords: function () {
    var content = this.data.content
    if (!content || !content.id) return
    wx.navigateTo({
      url: '/pages/detail/detail?id=' + content.id + '&tab=words'
    })
  },

  onStartReview: function () {
    wx.navigateTo({
      url: '/pages/review/review'
    })
  },

  onRetry: function () {
    this._loadTodayData(true)
  }
})
