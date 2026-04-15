const api = require('../../utils/api')
const storage = require('../../utils/storage')

Page({
  data: {
    // Mode: 'overview' | 'session' | 'summary'
    mode: 'overview',

    // Overview data
    loading: false,
    loadingDue: false,
    calendarDates: [],
    currentMonth: '',
    summary: null,
    dueCount: 0,

    // Session data
    dueItems: [],
    currentIndex: 0,
    currentItem: {},
    isFlipped: false,
    submitting: false,

    // Summary data
    summaryResult: {
      reviewedCount: 0,
      avgMastery: '0.0',
      masteryLabel: '',
      masteryLevel: '',
      distribution: []
    }
  },

  // Track mastery ratings during session
  _masteryRatings: [],

  onLoad() {
    this._initPage()
  },

  onShow() {
    // Refresh data when page becomes visible (e.g., coming back from another tab)
    if (this.data.mode === 'overview') {
      this._loadOverviewData()
    }
  },

  onPullDownRefresh() {
    this._loadOverviewData().then(function() {
      wx.stopPullDownRefresh()
    }).catch(function() {
      wx.stopPullDownRefresh()
    })
  },

  /**
   * Initialize page — set current month and load data
   */
  _initPage() {
    var now = new Date()
    var y = now.getFullYear()
    var m = String(now.getMonth() + 1).padStart(2, '0')
    this.setData({
      currentMonth: y + '-' + m
    })
    this._loadOverviewData()
  },

  /**
   * Load all overview data: calendar + summary + due count
   */
  _loadOverviewData() {
    var self = this
    self.setData({ loading: true })

    // Load calendar dates (from local cache + API)
    var calendarPromise = self._loadCalendarDates()

    // Load memory curve summary
    var summaryPromise = self._loadSummary()

    // Load due items count
    var duePromise = self._loadDueCount()

    return Promise.all([calendarPromise, summaryPromise, duePromise])
      .then(function() {
        self.setData({ loading: false })
      })
      .catch(function(err) {
        console.error('[Review] Failed to load overview:', err)
        self.setData({ loading: false })
      })
  },

  /**
   * Load study calendar dates
   * Uses local cache first, then refreshes from API
   */
  _loadCalendarDates() {
    var self = this

    // Try local cache first
    var cachedDates = storage.getStudyCalendar()
    if (cachedDates && cachedDates.length > 0) {
      self.setData({ calendarDates: cachedDates })
    }

    // Also fetch from API for the current month
    var parts = self.data.currentMonth.split('-')
    var params = {
      year: parseInt(parts[0]),
      month: parseInt(parts[1])
    }

    return api.get('/progress/calendar', params)
      .then(function(res) {
        var dates = res.dates || res.study_dates || []
        if (dates.length > 0) {
          self.setData({ calendarDates: dates })
        }
      })
      .catch(function(err) {
        console.warn('[Review] Failed to load calendar:', err)
        // Use local cache if available, silently fail
      })
  },

  /**
   * Load memory curve summary stats
   */
  _loadSummary() {
    var self = this

    return api.get('/progress/summary')
      .then(function(res) {
        self.setData({
          summary: {
            forgetting_count: res.forgetting_count || res.due_soon || 0,
            consolidating_count: res.consolidating_count || res.consolidating || 0,
            mastered_count: res.mastered_count || res.mastered || 0,
            new_count: res.new_count || res.new_items || 0
          }
        })
      })
      .catch(function(err) {
        console.warn('[Review] Failed to load summary:', err)
      })
  },

  /**
   * Load due items count (just count, not full items)
   */
  _loadDueCount() {
    var self = this
    self.setData({ loadingDue: true })

    return api.get('/review/due')
      .then(function(res) {
        var items = res.items || res.due_items || []
        self.setData({
          dueCount: items.length,
          loadingDue: false
        })
      })
      .catch(function(err) {
        console.warn('[Review] Failed to load due count:', err)
        self.setData({ loadingDue: false })
      })
  },

  /**
   * Calendar month change handler
   */
  onMonthChange(e) {
    var year = e.detail.year
    var month = e.detail.month
    var m = String(month).padStart(2, '0')
    this.setData({ currentMonth: year + '-' + m })
    this._loadCalendarDates()
  },

  /**
   * Calendar day tap handler
   */
  onDayTap(e) {
    // Could navigate to that day's content in the future
    var dateStr = e.detail.dateStr
    console.log('[Review] Tapped date:', dateStr)
  },

  /**
   * Start review session — fetch full due items and enter session mode
   */
  startReview() {
    var self = this
    if (self.data.dueCount === 0) return

    wx.showLoading({ title: '加载复习内容...' })

    api.get('/review/due')
      .then(function(res) {
        wx.hideLoading()
        var items = res.items || res.due_items || []

        if (items.length === 0) {
          wx.showToast({ title: '暂无待复习内容', icon: 'none' })
          return
        }

        self._masteryRatings = []
        self.setData({
          mode: 'session',
          dueItems: items,
          currentIndex: 0,
          currentItem: items[0],
          isFlipped: false,
          submitting: false
        })
      })
      .catch(function(err) {
        wx.hideLoading()
        console.error('[Review] Failed to load due items:', err)
        wx.showToast({ title: '加载失败，请重试', icon: 'none' })
      })
  },

  /**
   * Flip the current card
   */
  flipCard() {
    this.setData({
      isFlipped: !this.data.isFlipped
    })
  },

  /**
   * Select mastery level and advance to next card
   */
  selectMastery(e) {
    var self = this
    if (self.data.submitting) return

    var mastery = parseInt(e.currentTarget.dataset.mastery)
    var currentItem = self.data.currentItem

    self.setData({ submitting: true })

    // Submit mastery to API
    var postData = {
      item_id: currentItem.id,
      item_type: currentItem.type || currentItem.item_type || 'phrase',
      mastery: mastery
    }
    if (currentItem.word_id) {
      postData.word_id = currentItem.word_id
    }
    if (currentItem.phrase_id) {
      postData.phrase_id = currentItem.phrase_id
    }

    api.post('/review/complete', postData)
      .then(function(res) {
        // Record the mastery rating locally
        self._masteryRatings.push({
          text: currentItem.text,
          mastery: mastery
        })

        // Record study day
        storage.recordStudyDay()

        // Move to next card or show summary
        var nextIndex = self.data.currentIndex + 1
        if (nextIndex >= self.data.dueItems.length) {
          // Session complete — show summary
          self._showSummary()
        } else {
          self.setData({
            currentIndex: nextIndex,
            currentItem: self.data.dueItems[nextIndex],
            isFlipped: false,
            submitting: false
          })
        }
      })
      .catch(function(err) {
        console.error('[Review] Failed to submit mastery:', err)
        self.setData({ submitting: false })
        wx.showToast({ title: '提交失败，请重试', icon: 'none' })
      })
  },

  /**
   * Show review summary after session completes
   */
  _showSummary() {
    var ratings = this._masteryRatings
    var totalCount = ratings.length

    if (totalCount === 0) {
      this.setData({
        mode: 'summary',
        summaryResult: {
          reviewedCount: 0,
          avgMastery: '0.0',
          masteryLabel: '无数据',
          masteryLevel: 'none',
          distribution: []
        }
      })
      return
    }

    // Calculate average mastery
    var sum = 0
    for (var i = 0; i < ratings.length; i++) {
      sum += ratings[i].mastery
    }
    var avg = sum / totalCount
    var avgStr = avg.toFixed(1)

    // Determine overall mastery label
    var masteryLabel = ''
    var masteryLevel = ''
    if (avg >= 3.5) {
      masteryLabel = '太棒了！'
      masteryLevel = 'excellent'
    } else if (avg >= 2.5) {
      masteryLabel = '不错哦！'
      masteryLevel = 'good'
    } else if (avg >= 1.5) {
      masteryLabel = '继续加油'
      masteryLevel = 'fair'
    } else {
      masteryLabel = '需要复习'
      masteryLevel = 'poor'
    }

    // Calculate distribution
    var distLabels = [
      { level: 0, emoji: '😫', label: '完全忘了' },
      { level: 1, emoji: '😕', label: '有点印象' },
      { level: 2, emoji: '🤔', label: '想起来了' },
      { level: 3, emoji: '😊', label: '比较熟悉' },
      { level: 4, emoji: '🎯', label: '完全掌握' }
    ]

    var distribution = []
    for (var j = 0; j < distLabels.length; j++) {
      var count = 0
      for (var k = 0; k < ratings.length; k++) {
        if (ratings[k].mastery === distLabels[j].level) {
          count++
        }
      }
      distribution.push({
        level: distLabels[j].level,
        emoji: distLabels[j].emoji,
        label: distLabels[j].label,
        count: count,
        pct: totalCount > 0 ? Math.round((count / totalCount) * 100) : 0
      })
    }

    this.setData({
      mode: 'summary',
      submitting: false,
      summaryResult: {
        reviewedCount: totalCount,
        avgMastery: avgStr,
        masteryLabel: masteryLabel,
        masteryLevel: masteryLevel,
        distribution: distribution
      }
    })
  },

  /**
   * Exit review session early — confirm with user
   */
  exitSession() {
    var self = this
    var reviewed = self._masteryRatings.length
    var total = self.data.dueItems.length

    if (reviewed > 0 && reviewed < total) {
      wx.showModal({
        title: '确认退出',
        content: '已完成 ' + reviewed + '/' + total + ' 项，确定退出吗？',
        confirmText: '退出',
        cancelText: '继续复习',
        success: function(res) {
          if (res.confirm) {
            self._showSummary()
          }
        }
      })
    } else {
      self.backToOverview()
    }
  },

  /**
   * Review again — reload due items and start new session
   */
  reviewAgain() {
    this.setData({ mode: 'overview' })
    this.startReview()
  },

  /**
   * Back to overview mode
   */
  backToOverview() {
    this._masteryRatings = []
    this.setData({
      mode: 'overview',
      currentIndex: 0,
      currentItem: {},
      isFlipped: false,
      submitting: false
    })
    // Refresh overview data
    this._loadOverviewData()
  },

  /**
   * Share review result
   */
  onShareAppMessage() {
    if (this.data.mode === 'summary') {
      var result = this.data.summaryResult
      return {
        title: '我刚刚复习了' + result.reviewedCount + '个短语，掌握度' + result.avgMastery + '！',
        path: '/pages/review/review'
      }
    }
    return {
      title: 'EasySpeak · 智能复习',
      path: '/pages/review/review'
    }
  }
})
