/**
 * EasySpeak - Quiz Page (测验中心 - Tab 4)
 * 4 quiz modes: Lightning, Theme, Wrong Review, Stats
 */

const api = require('../../utils/api')
const auth = require('../../utils/auth')

Page({
  data: {
    loading: true,
    // Quiz stats
    stats: {
      total_answered: 0,
      accuracy: 0,
      current_streak: 0,
      max_streak: 0
    },
    // Theme list for theme quiz
    themes: [],
    selectedThemes: [],
    // Wrong question count
    wrongCount: 0,
    // UI state
    showThemePicker: false,
    showStatsPanel: false
  },

  onLoad: function () {
    // nothing
  },

  onShow: function () {
    this._loadStats()
    this._loadThemes()
  },

  onPullDownRefresh: function () {
    var self = this
    Promise.all([self._loadStats(), self._loadThemes()])
      .then(function () {
        wx.stopPullDownRefresh()
      })
      .catch(function () {
        wx.stopPullDownRefresh()
      })
  },

  // ========================
  // Data Loading
  // ========================

  _loadStats: function () {
    var self = this
    return auth.ensureLogin().then(function (loggedIn) {
      if (!loggedIn) {
        self.setData({ loading: false })
        return
      }
      return api.get('/quiz/stats').then(function (data) {
        var stats = data || {}
        self.setData({
          loading: false,
          stats: {
            total_answered: stats.total_answered || 0,
            accuracy: stats.accuracy || 0,
            current_streak: stats.current_streak || 0,
            max_streak: stats.max_streak || 0
          },
          wrongCount: stats.wrong_count || 0
        })
      }).catch(function (err) {
        console.error('[Quiz] Failed to load stats:', err)
        self.setData({ loading: false })
      })
    })
  },

  _loadThemes: function () {
    var self = this
    return auth.ensureLogin().then(function (loggedIn) {
      if (!loggedIn) return
      return api.get('/daily/themes').then(function (data) {
        var themes = (data || []).map(function (t) {
          return {
            id: t.id,
            theme_zh: t.theme_zh || '',
            theme_en: t.theme_en || ''
          }
        })
        self.setData({ themes: themes })
      }).catch(function (err) {
        console.error('[Quiz] Failed to load themes:', err)
      })
    })
  },

  // ========================
  // Navigation
  // ========================

  /** ⚡ 闪电测验 */
  onStartLightning: function () {
    wx.navigateTo({
      url: '/pages/quiz-play/quiz-play?type=lightning&count=10&mode=timed'
    })
  },

  /** 🧩 填空挑战 */
  onStartFillBlank: function () {
    wx.navigateTo({
      url: '/pages/quiz-play/quiz-play?type=fill_blank&count=10&mode=normal'
    })
  },

  /** 📝 主题测验 - open picker */
  onToggleThemePicker: function () {
    this.setData({
      showThemePicker: !this.data.showThemePicker,
      selectedThemes: []
    })
  },

  /** Theme selection toggle */
  onThemeSelect: function (e) {
    var id = e.currentTarget.dataset.id
    var selected = this.data.selectedThemes
    var idx = selected.indexOf(id)
    if (idx === -1) {
      selected.push(id)
    } else {
      selected.splice(idx, 1)
    }
    this.setData({ selectedThemes: selected })
  },

  /** Start theme quiz */
  onStartThemeQuiz: function () {
    var ids = this.data.selectedThemes
    if (ids.length === 0) {
      wx.showToast({ title: '请至少选择一个主题', icon: 'none' })
      return
    }
    var contentId = ids.join(',')
    wx.navigateTo({
      url: '/pages/quiz-play/quiz-play?type=theme&count=10&contentId=' + contentId + '&mode=normal'
    })
  },

  /** 🔄 错题回顾 */
  onStartWrongReview: function () {
    if (this.data.wrongCount === 0) {
      wx.showToast({ title: '暂无错题，继续加油！', icon: 'none' })
      return
    }
    wx.navigateTo({
      url: '/pages/quiz-play/quiz-play?type=wrong&count=' + Math.min(this.data.wrongCount, 20) + '&mode=normal'
    })
  },

  /** 📊 测验统计 - toggle panel */
  onToggleStats: function () {
    this.setData({ showStatsPanel: !this.data.showStatsPanel })
  }
})
