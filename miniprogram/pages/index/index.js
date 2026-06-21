/**
 * EasySpeak - Index Page (首页)
 * Displays today's push content, phrases, words, progress, and review reminder.
 */

const api = require('../../utils/api')
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')

// Date helpers
const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
const LOAD_PROGRESS_INTERVAL = 260

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
    loadingProgress: 0,
    loadingText: '正在连接今日内容...',

    // Date picker
    currentDate: formatDateStr(new Date()),
 currentDateDisplay: '',
 currentWeekday: '',

 // Today's content
 content: null,
    tomorrowTheme: null,
    tomorrowDateDisplay: '',
    tomorrowWeekday: '',

    phrases: [],

    // Words list
    words: [],

    // Progress
    phraseProgress: { current: 0, total: 5 },
    wordProgress: { current: 0, total: 20 },
    canLearnPhrase: true,
    canLearnWord: true,
    allLearnedToday: false,

    // Review
    reviewDueCount: 0,

    // Empty state
    isEmpty: false,

    // Error state
    error: false,
    errorMsg: '',

    isToday: true,

    // Calendar Popup
    showCalendar: false,
    calendarYear: 2026,
    calendarMonth: 4,
    calendarDays: []
  },

  _loadProgressTimer: null,

  onLoad: function () {
    this._initDate()
  },

  onUnload: function () {
    this._clearLoadProgress()
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
    var theme = ''
    if (this.data.content) {
      theme = this.data.content.theme_zh || ''
    }
    return {
      title: 'EasySpeak · ' + theme,
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
      currentWeekday: getWeekday(dateStr),
      isToday: true
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
        if (self.data.isToday && cached.tomorrow) {
          self._processTomorrowDataFromResponse(cached.tomorrow)
        }
        self.setData({ loading: false })
        // Still fetch in background to refresh cache
        self._fetchFromServer(dateStr, { silent: true })
        return Promise.resolve()
      }
    }

    return self._fetchFromServer(dateStr)
  },

  _fetchFromServer: function (dateStr, options) {
    var self = this
    options = options || {}
    var silent = !!options.silent
    if (!silent) {
      self.setData({
        loading: true,
        error: false,
        isEmpty: false,
        loadingProgress: 0,
        loadingText: '正在连接今日内容...'
      })
      self._startLoadProgress()
    }

    return auth.ensureLogin().then(function (loggedIn) {
      if (!loggedIn) {
        // Still allow viewing without login for content
        console.log('[Index] Login failed, fetching without auth')
      }
      return api.get('/daily/today', { target_date: dateStr })
    }).then(function (data) {
      console.log('[Index] API response:', data)
      // Cache the result
      storage.setDailyCache(dateStr, data)
      self._processData(data)
      // Use tomorrow data from API response (no extra request needed)
      if (self.data.isToday && data && data.tomorrow) {
        self._processTomorrowDataFromResponse(data.tomorrow)
      } else {
        self.setData({ tomorrowTheme: null, tomorrowDateDisplay: '', tomorrowWeekday: '' })
      }
      if (!silent) {
        self._finishLoadProgress(function () {
          self.setData({ loading: false, refreshing: false })
        })
      } else {
        self.setData({ refreshing: false })
      }
    }).catch(function (err) {
      console.error('[Index] Fetch failed:', err)
      if (!silent) {
        self._clearLoadProgress()
      }
      self.setData({
        loading: silent ? self.data.loading : false,
        refreshing: false,
        error: silent ? self.data.error : true,
        errorMsg: err.message || '加载失败'
      })
      // If we had cached data before, still show it
      var cached = storage.getDailyCache(dateStr)
      if (cached) {
        self._processData(cached)
        if (self.data.isToday && cached.tomorrow) {
          self._processTomorrowDataFromResponse(cached.tomorrow)
        }
        self.setData({ error: false, loading: false })
      }
    })
  },

  _startLoadProgress: function () {
    var self = this
    self._clearLoadProgress()
    self._loadProgressTimer = setInterval(function () {
      var current = self.data.loadingProgress || 0
      if (current >= 96) {
        self.setData({ loadingText: '内容马上就好，请稍等...' })
        return
      }

      var next = current + (current < 35 ? 12 : current < 70 ? 7 : current < 90 ? 4 : 1)
      if (next > 96) next = 96

      var text = '正在连接今日内容...'
      if (next >= 35 && next < 70) {
        text = '正在整理短语和单词...'
      } else if (next >= 70 && next < 90) {
        text = '正在同步学习进度...'
      } else if (next >= 90) {
        text = '正在准备首页卡片...'
      }

      self.setData({
        loadingProgress: next,
        loadingText: text
      })
    }, LOAD_PROGRESS_INTERVAL)
  },

  _clearLoadProgress: function () {
    if (this._loadProgressTimer) {
      clearInterval(this._loadProgressTimer)
      this._loadProgressTimer = null
    }
  },

  _finishLoadProgress: function (done) {
    this._clearLoadProgress()
    this.setData({
      loadingProgress: 100,
      loadingText: '今日内容已准备好'
    })
    setTimeout(function () {
      if (typeof done === 'function') done()
    }, 160)
  },

  _processTomorrowDataFromResponse: function (tomorrow) {
    if (!tomorrow || !tomorrow.theme_zh) {
      this.setData({ tomorrowTheme: null, tomorrowDateDisplay: '', tomorrowWeekday: '' })
      return
    }
    // Calculate tomorrow's date display
    var tomorrowDate = new Date()
    tomorrowDate.setDate(tomorrowDate.getDate() + 1)
    var tomorrowStr = formatDateStr(tomorrowDate)
    this.setData({
      tomorrowTheme: {
        theme_zh: tomorrow.theme_zh || '',
        theme_en: tomorrow.theme_en || '',
        category_zh: tomorrow.category_zh || ''
      },
      tomorrowDateDisplay: formatDisplayDate(tomorrowStr),
      tomorrowWeekday: getWeekday(tomorrowStr)
    })
  },

 _processData: function (data) {
 if (!data || !data.content) {
 this.setData({ isEmpty: true, content: null, phrases: [], words: [] })
 return
 }

 var content = data.content

 var phrases = (content.phrases || []).map(function (p) {
 return {
 id: p.id,
 phrase: p.phrase || '',
 meaning: p.meaning || '',
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
 example: w.example || '',
 usageNote: w.usage_note || '',
 contextMeanings: w.context_meanings || []
 }
 })

 this.setData({
 content: content,
 isEmpty: false,
 phrases: phrases,
 words: words
 })

    // Progress
    var progress = data.progress || {}
    var phraseCurrent = progress.phrases_learned || 0
    var phraseTotal = progress.phrases_total || phrases.length
    var wordCurrent = progress.words_learned || 0
    var wordTotal = progress.words_total || words.length
    var canLearnPhrase = phraseTotal > 0 ? phraseCurrent < phraseTotal : false
    var canLearnWord = wordTotal > 0 ? wordCurrent < wordTotal : false
    this.setData({
      phraseProgress: {
        current: phraseCurrent,
        total: phraseTotal
      },
      wordProgress: {
        current: wordCurrent,
        total: wordTotal
      },
      canLearnPhrase: canLearnPhrase,
      canLearnWord: canLearnWord,
      allLearnedToday: phraseTotal > 0 && wordTotal > 0 && !canLearnPhrase && !canLearnWord
    })

    // Review
    var review = data.review || {}
    this.setData({
      reviewDueCount: review.due_count || 0
    })
  },

  // ========================
  // Event Handlers
  // ========================

  onOpenCalendar: function () {
    var d = new Date(this.data.currentDate + 'T00:00:00')
    this.setData({
      showCalendar: true,
      calendarYear: d.getFullYear(),
      calendarMonth: d.getMonth() + 1
    })
    this._loadCalendarData(this.data.calendarYear, this.data.calendarMonth)
  },

  onCloseCalendar: function () {
    this.setData({ showCalendar: false })
  },

  onPrevMonth: function () {
    var y = this.data.calendarYear
    var m = this.data.calendarMonth - 1
    if (m < 1) { m = 12; y-- }
    this.setData({ calendarYear: y, calendarMonth: m })
    this._loadCalendarData(y, m)
  },

  onNextMonth: function () {
    var today = new Date()
    var ty = today.getFullYear()
    var tm = today.getMonth() + 1
    var y = this.data.calendarYear
    var m = this.data.calendarMonth + 1
    if (m > 12) { m = 1; y++ }
    if (y > ty || (y === ty && m > tm)) {
      wx.showToast({ title: '不能查看未来月份哦', icon: 'none' })
      return
    }
    this.setData({ calendarYear: y, calendarMonth: m })
    this._loadCalendarData(y, m)
  },

  onSelectCalendarDate: function (e) {
    var ds = e.currentTarget.dataset
    if (ds.empty || !ds.has) return
    this.setData({ showCalendar: false })
    if (ds.date === this.data.currentDate) return

    this.setData({
      currentDate: ds.date,
      currentDateDisplay: formatDisplayDate(ds.date),
      currentWeekday: getWeekday(ds.date),
      isToday: ds.date === formatDateStr(new Date())
    })
    this._loadTodayData()
  },

  _loadCalendarData: function (y, m) {
    var self = this
    wx.showLoading({ title: '加载中...', mask: true })
    api.get('/daily/calendar', { year: y, month: m })
      .then(function (data) {
        wx.hideLoading()
        self._buildCalendarGrid(y, m, data.items || [])
      })
      .catch(function (err) {
        wx.hideLoading()
        wx.showToast({ title: '日历加载失败', icon: 'none' })
      })
  },

  _buildCalendarGrid: function (year, month, items) {
    var firstDay = new Date(year, month - 1, 1).getDay()
    var daysInMonth = new Date(year, month, 0).getDate()

    var itemsMap = {}
    items.forEach(function(item) {
      itemsMap[item.date] = item
    })

    var grid = []

    for (var i = 0; i < firstDay; i++) {
      grid.push({ empty: true })
    }

    var todayStr = formatDateStr(new Date())
    var currentStr = this.data.currentDate

    for (var i = 1; i <= daysInMonth; i++) {
      var dStr = year + '-' + String(month).padStart(2, '0') + '-' + String(i).padStart(2, '0')
      var hasItem = itemsMap[dStr]
      var theme = hasItem ? hasItem.theme_zh : ''
      var displayTheme = theme.length > 4 ? theme.substring(0, 3) + '…' : theme

      grid.push({
        empty: false,
        day: i,
        dateStr: dStr,
        theme_zh: displayTheme,
        hasContent: !!hasItem,
        isToday: dStr === todayStr,
        isSelected: dStr === currentStr
      })
    }
    this.setData({ calendarDays: grid })
  },

  onPrevDate: function () {
    var current = new Date(this.data.currentDate + 'T00:00:00')
    current.setDate(current.getDate() - 1)
    var newDateStr = formatDateStr(current)
    var todayStr = formatDateStr(new Date())
    this.setData({
      currentDate: newDateStr,
      currentDateDisplay: formatDisplayDate(newDateStr),
      currentWeekday: getWeekday(newDateStr),
      isToday: newDateStr === todayStr
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
      currentWeekday: getWeekday(newDateStr),
      isToday: newDateStr === today
    })
    this._loadTodayData()
  },

  onBackToToday: function () {
    var today = formatDateStr(new Date())
    if (this.data.currentDate === today) return
    this.setData({
      currentDate: today,
      currentDateDisplay: formatDisplayDate(today),
      currentWeekday: getWeekday(today),
      isToday: true
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

  onStartLearnPhrase: function () {
    this._startLearn('phrase')
  },

  onStartLearnWord: function () {
    this._startLearn('word')
  },

  _startLearn: function (learnType) {
    var content = this.data.content
    if (!content || !content.id) return
    var draft = storage.getLearnDraft(content.id, learnType)
    var url = '/pages/learn-session/learn-session?contentId=' + content.id + '&learnType=' + learnType

    if (draft) {
      wx.showActionSheet({
        itemList: ['继续上次学习', '重新开始'],
        success: function (res) {
          if (res.tapIndex === 0) {
            wx.navigateTo({ url: url + '&resume=1' })
          } else if (res.tapIndex === 1) {
            storage.removeLearnDraft(content.id, learnType)
            wx.navigateTo({ url: url })
          }
        }
      })
      return
    }

    wx.navigateTo({
      url: url
    })
  },

  onPhraseToggle: function (e) {
    // Phrase card expanded/collapsed — handled by component internally
  },

  onStartReview: function () {
    wx.switchTab({
      url: '/pages/review/review'
    })
  },

  onRetry: function () {
    this._loadTodayData(true)
  }
})
