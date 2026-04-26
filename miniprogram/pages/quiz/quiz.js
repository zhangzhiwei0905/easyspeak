const api = require('../../utils/api')
const auth = require('../../utils/auth')

Page({
  data: {
    loading: true,
    stats: {
      total_answered: 0,
      accuracy: 0,
      current_streak: 0,
      max_streak: 0,
      wrong_count: 0
    },
    themes: [],
    selectedThemes: [],
    wrongCount: 0,
    showThemePicker: false,
    showStatsPanel: false
  },

  onShow: function () {
    this._loadData()
  },

  onPullDownRefresh: function () {
    this._loadData()
      .then(function () {
        wx.stopPullDownRefresh()
      })
      .catch(function () {
        wx.stopPullDownRefresh()
      })
  },

  _loadData: function () {
    var self = this
    self.setData({ loading: true })

    return auth.ensureLogin().then(function (loggedIn) {
      if (!loggedIn) {
        self.setData({ loading: false })
        return
      }

      return Promise.all([
        self._loadStats(),
        self._loadThemes()
      ]).then(function () {
        self.setData({ loading: false })
      }).catch(function (err) {
        self.setData({ loading: false })
        throw err
      })
    })
  },

  _loadStats: function () {
    var self = this
    return api.get('/quiz/stats')
      .then(function (data) {
        var stats = data || {}
        self.setData({
          stats: {
            total_answered: stats.total_answered || 0,
            accuracy: stats.accuracy || 0,
            current_streak: stats.current_streak || 0,
            max_streak: stats.max_streak || 0,
            wrong_count: stats.wrong_count || 0
          },
          wrongCount: stats.wrong_count || 0
        })
      })
      .catch(function (err) {
        console.error('[Quiz] Failed to load stats:', err)
      })
  },

  _loadThemes: function () {
    var self = this
    return api.get('/quiz/themes')
      .then(function (data) {
        self.setData({
          themes: (data || []).map(function (item) {
            return {
              content_id: parseInt(item.content_id, 10),
              theme_zh: item.theme_zh || '',
              theme_en: item.theme_en || '',
              question_count: item.question_count || 0,
              selected: false
            }
          })
        })
      })
      .catch(function (err) {
        console.error('[Quiz] Failed to load themes:', err)
      })
  },

  _goToQuizPlay: function (params) {
    var query = Object.keys(params)
      .filter(function (key) {
        return params[key] !== undefined && params[key] !== null && params[key] !== ''
      })
      .map(function (key) {
        return encodeURIComponent(key) + '=' + encodeURIComponent(params[key])
      })
      .join('&')

    wx.navigateTo({
      url: '/pages/quiz-play/quiz-play?' + query
    })
  },

  onStartLightning: function () {
    this._goToQuizPlay({
      mode: 'random',
      questionCount: 10,
      quizMode: 'timed'
    })
  },

  onToggleThemePicker: function () {
    var opening = !this.data.showThemePicker
    var themes = this.data.themes
    if (!opening) {
      themes = themes.map(function (item) {
        return Object.assign({}, item, { selected: false })
      })
    }
    this.setData({
      showThemePicker: opening,
      selectedThemes: opening ? this.data.selectedThemes : [],
      themes: themes
    })
  },

  onThemeSelect: function (e) {
    var id = parseInt(e.currentTarget.dataset.id, 10)
    var selected = this.data.selectedThemes.slice()
    var idx = selected.indexOf(id)

    if (idx === -1) {
      selected.push(id)
    } else {
      selected.splice(idx, 1)
    }

    var themes = this.data.themes.map(function (item) {
      return Object.assign({}, item, {
        selected: selected.indexOf(item.content_id) !== -1
      })
    })

    this.setData({
      selectedThemes: selected,
      themes: themes
    })
  },

  onStartThemeQuiz: function () {
    var ids = this.data.selectedThemes
    if (ids.length === 0) {
      wx.showToast({ title: '请至少选择一个主题', icon: 'none' })
      return
    }

    this._goToQuizPlay({
      mode: 'theme',
      questionCount: 10,
      contentIds: ids.join(','),
      quizMode: 'normal'
    })
  },

  onStartWrongReview: function () {
    if (this.data.wrongCount === 0) {
      wx.showToast({ title: '暂无错题，继续加油！', icon: 'none' })
      return
    }

    this._goToQuizPlay({
      mode: 'wrong_review',
      questionCount: Math.min(this.data.wrongCount, 20),
      quizMode: 'normal'
    })
  },

  onToggleStats: function () {
    this.setData({ showStatsPanel: !this.data.showStatsPanel })
  }
})
