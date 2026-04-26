const api = require('../../utils/api')
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')

Page({
  data: {
    mode: 'overview',

    loading: false,
    currentMonth: '',
    calendarData: [],
    summary: {
      forgetting_count: 0,
      consolidating_count: 0,
      mastered_count: 0,
      new_count: 0
    },
    dueCount: 0,
    overviewLoadFailed: false,

    dueItems: [],
    currentIndex: 0,
    currentItem: {},
    isFlipped: false,
    submitting: false,

    summaryResult: {
      reviewedCount: 0,
      avgMastery: '0.0',
      masteryLabel: '',
      masteryLevel: '',
      distribution: []
    },

    showDayDetail: false,
    dayDetail: {}
  },

  _masteryRatings: [],

  onLoad() {
    this._initPage()
  },

  onShow() {
    if (this.data.mode === 'overview') {
      this._loadOverviewData()
    }
  },

  onPullDownRefresh() {
    this._loadOverviewData()
      .then(function () {
        wx.stopPullDownRefresh()
      })
      .catch(function () {
        wx.stopPullDownRefresh()
      })
  },

  _initPage() {
    var now = new Date()
    var y = now.getFullYear()
    var m = String(now.getMonth() + 1).padStart(2, '0')
    this.setData({
      currentMonth: y + '-' + m
    })
    this._loadOverviewData()
  },

  _loadOverviewData() {
    var self = this
    var parts = self.data.currentMonth.split('-')
    var params = {
      year: parseInt(parts[0], 10),
      month: parseInt(parts[1], 10)
    }

    self.setData({
      loading: true,
      overviewLoadFailed: false
    })

    return auth.ensureLogin()
      .then(function (loggedIn) {
        if (!loggedIn) {
          self.setData({
            loading: false,
            overviewLoadFailed: true
          })
          return Promise.reject(new Error('login required'))
        }

        return api.get('/review/overview', params)
      })
      .then(function (res) {
        var rawCalendar = res.calendar_dates || []
        // Handle both formats: old API returns strings, new API returns objects
        var calendarData = []
        var dateStrings = []
        for (var i = 0; i < rawCalendar.length; i++) {
          var item = rawCalendar[i]
          if (typeof item === 'string') {
            calendarData.push({ date: item, has_content: false, learned: false, reviewed: 0 })
            dateStrings.push(item)
          } else {
            calendarData.push(item)
            dateStrings.push(item.date)
          }
        }

        self.setData({
          loading: false,
          overviewLoadFailed: false,
          calendarData: calendarData,
          dueCount: res.due_count || 0,
          summary: res.memory_summary || {
            forgetting_count: 0,
            consolidating_count: 0,
            mastered_count: 0,
            new_count: 0
          }
        })

        if (dateStrings.length > 0) {
          storage.set(storage.KEYS.STUDY_CALENDAR, dateStrings)
        }
      })
      .catch(function (err) {
        console.error('[Review] Failed to load overview:', err)
        self.setData({
          loading: false,
          overviewLoadFailed: true
        })
      })
  },

  onMonthChange(e) {
    var year = e.detail.year
    var month = e.detail.month
    var m = String(month).padStart(2, '0')
    this.setData({ currentMonth: year + '-' + m })
    this._loadOverviewData()
  },

  onDayTap(e) {
    var dayData = e.detail.dayData
    if (!dayData || !dayData.dateStr) return
    if (dayData.status === 'empty') return
    if (dayData.status === 'none' && !dayData.reviewed) return

    this.setData({
      showDayDetail: true,
      dayDetail: {
        dateStr: dayData.dateStr,
        hasReview: (dayData.reviewed || 0) > 0,
        hasContent: !!(dayData.themeZh || dayData.phraseCount || dayData.wordCount),
        themeZh: dayData.themeZh || '',
        phraseCount: dayData.phraseCount || 0,
        wordCount: dayData.wordCount || 0,
        firstPassRate: dayData.firstPassRate,
        avgMastery: dayData.avgMastery || 0,
        reviewed: dayData.reviewed || 0,
        reviewedCount: dayData.reviewedCount || dayData.reviewed || 0,
        reviewPhraseCount: dayData.reviewPhraseCount || 0,
        reviewWordCount: dayData.reviewWordCount || 0,
        forgotCount: dayData.forgotCount || 0,
        fuzzyCount: dayData.fuzzyCount || 0,
        rememberedCount: dayData.rememberedCount || 0,
        solidCount: dayData.solidCount || 0,
        status: dayData.status
      }
    })
  },

  closeDayDetail() {
    this.setData({ showDayDetail: false })
  },

  startReview() {
    var self = this
    if (self.data.loading) return

    wx.showLoading({ title: '加载复习内容...' })
    auth.ensureLogin()
      .then(function (loggedIn) {
        if (!loggedIn) {
          wx.hideLoading()
          return Promise.reject(new Error('login required'))
        }
        return api.get('/review/due')
      })
      .then(function (res) {
        wx.hideLoading()
        var items = res.items || []

        if (items.length === 0) {
          wx.showToast({ title: '暂无待复习内容', icon: 'none' })
          self._loadOverviewData()
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
      .catch(function (err) {
        wx.hideLoading()
        console.error('[Review] Failed to load due items:', err)
        wx.showToast({ title: '加载失败，请重试', icon: 'none' })
      })
  },

  flipCard() {
    this.setData({
      isFlipped: !this.data.isFlipped
    })
  },

  selectMastery(e) {
    var self = this
    if (self.data.submitting) return

    var mastery = parseInt(e.currentTarget.dataset.mastery, 10)
    var currentItem = self.data.currentItem

    self.setData({ submitting: true })

    api.post('/review/complete', {
      item_id: currentItem.id,
      item_type: currentItem.item_type,
      mastery: mastery
    })
      .then(function () {
        self._masteryRatings.push({
          text: currentItem.text,
          mastery: mastery
        })

        storage.recordStudyDay()

        var nextIndex = self.data.currentIndex + 1
        if (nextIndex >= self.data.dueItems.length) {
          self._showSummary()
          return
        }

        self.setData({
          currentIndex: nextIndex,
          currentItem: self.data.dueItems[nextIndex],
          isFlipped: false,
          submitting: false
        })
      })
      .catch(function (err) {
        console.error('[Review] Failed to submit mastery:', err)
        self.setData({ submitting: false })
        wx.showToast({ title: '提交失败，请重试', icon: 'none' })
      })
  },

  _showSummary() {
    var ratings = this._masteryRatings
    var totalCount = ratings.length

    if (totalCount === 0) {
      this.setData({
        mode: 'summary',
        submitting: false,
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

    var sum = 0
    for (var i = 0; i < ratings.length; i++) {
      sum += ratings[i].mastery
    }
    var avg = sum / totalCount

    var masteryLabel = '需要复习'
    var masteryLevel = 'poor'
    if (avg >= 3.5) {
      masteryLabel = '太棒了！'
      masteryLevel = 'excellent'
    } else if (avg >= 2.5) {
      masteryLabel = '不错哦！'
      masteryLevel = 'good'
    } else if (avg >= 1.5) {
      masteryLabel = '继续加油'
      masteryLevel = 'fair'
    }

    var labels = [
      { level: 0, emoji: '😫', label: '完全忘了' },
      { level: 1, emoji: '😕', label: '有点印象' },
      { level: 2, emoji: '🤔', label: '想起来了' },
      { level: 3, emoji: '😊', label: '比较熟悉' },
      { level: 4, emoji: '🎯', label: '完全掌握' }
    ]

    var distribution = labels.map(function (entry) {
      var count = ratings.filter(function (item) {
        return item.mastery === entry.level
      }).length
      return {
        level: entry.level,
        emoji: entry.emoji,
        label: entry.label,
        count: count,
        pct: totalCount > 0 ? Math.round((count / totalCount) * 100) : 0
      }
    })

    this.setData({
      mode: 'summary',
      submitting: false,
      summaryResult: {
        reviewedCount: totalCount,
        avgMastery: avg.toFixed(1),
        masteryLabel: masteryLabel,
        masteryLevel: masteryLevel,
        distribution: distribution
      }
    })
  },

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
        success: function (res) {
          if (res.confirm) {
            self._showSummary()
          }
        }
      })
      return
    }

    self.backToOverview()
  },

  reviewAgain() {
    this.setData({ mode: 'overview' })
    this.startReview()
  },

  backToOverview() {
    this._masteryRatings = []
    this.setData({
      mode: 'overview',
      currentIndex: 0,
      currentItem: {},
      isFlipped: false,
      submitting: false
    })
    this._loadOverviewData()
  },

  goToQuiz() {
    wx.switchTab({
      url: '/pages/quiz/quiz'
    })
  },

  onShareAppMessage() {
    if (this.data.mode === 'summary') {
      var result = this.data.summaryResult
      return {
        title: '我刚刚复习了' + result.reviewedCount + '项内容，掌握度' + result.avgMastery + '！',
        path: '/pages/review/review'
      }
    }

    return {
      title: 'EasySpeak · 智能复习',
      path: '/pages/review/review'
    }
  }
})
