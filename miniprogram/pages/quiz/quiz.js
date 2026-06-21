var api = require('../../utils/api')
var auth = require('../../utils/auth')

function buildCategoryFilters(categories, selectedKeys) {
  var selectedMap = {}
  ;(selectedKeys || []).forEach(function (key) {
    selectedMap[key] = true
  })

  return (categories || []).map(function (item) {
    var key = String(item.key)
    return {
      key: key,
      label: item.label || key,
      selected: !!selectedMap[key]
    }
  })
}

function clampPercent(value) {
  var numeric = Number(value) || 0
  if (numeric < 0) return 0
  if (numeric > 100) return 100
  return Math.round(numeric)
}

function buildDisplayStats(stats) {
  var accuracy = clampPercent(stats.accuracy)
  var totalAnswered = Number(stats.total_answered) || 0
  var streakDays = Number(stats.streak_days) || 0
  var wrongCount = Number(stats.wrong_count) || 0
  var weeklyGoal = Number(stats.weekly_goal) || 50
  var weeklyDone = Number(stats.weekly_answered) || 0
  var weeklyPercent = clampPercent(stats.weekly_percent)

  return {
    streakDays: streakDays,
    doneText: totalAnswered || 0,
    weeklyDone: weeklyDone,
    weeklyGoal: weeklyGoal,
    weeklyPercent: weeklyPercent,
    weeklyRing: 'conic-gradient(#ffb21c ' + weeklyPercent + '%, #edf1f8 ' + weeklyPercent + '%)',
    accuracy: accuracy,
    accuracyRing: 'conic-gradient(#2f73ff ' + accuracy + '%, #edf1f8 ' + accuracy + '%)',
    wrongStatus: wrongCount > 0 ? '待复盘' : '已清空'
  }
}

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
    wrongCount: 0,
    displayStats: buildDisplayStats({}),
    showStatsPanel: false,
    showCategoryPicker: false,
    categoriesLoading: false,
    availableCategories: [],
    categoryFilters: buildCategoryFilters([], []),
    selectedCategories: []
  },

  onShow: function () {
    this._loadData()
  },

  onPullDownRefresh: function () {
    var self = this
    self._loadData()
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

      return Promise.all([self._loadStats(), self._loadCategories()]).then(function () {
        self.setData({ loading: false })
      })
    }).catch(function () {
      self.setData({ loading: false })
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
            streak_days: stats.streak_days || 0,
            weekly_answered: stats.weekly_answered || 0,
            weekly_goal: stats.weekly_goal || 50,
            weekly_percent: stats.weekly_percent || 0,
            wrong_count: stats.wrong_count || 0
          },
          wrongCount: stats.wrong_count || 0,
          displayStats: buildDisplayStats(stats)
        })
      })
      .catch(function (err) {
        console.error('[Quiz] Failed to load stats:', err)
      })
  },

  _loadCategories: function () {
    var self = this
    self.setData({ categoriesLoading: true })
    return api.get('/quiz/categories')
      .then(function (data) {
        var categories = Array.isArray(data) ? data.filter(function (item) {
          return item && item.key && (item.question_count || 0) > 0
        }) : []

        self.setData({
          categoriesLoading: false,
          availableCategories: categories,
          categoryFilters: buildCategoryFilters(categories, self.data.selectedCategories)
        })
      })
      .catch(function (err) {
        console.error('[Quiz] Failed to load categories:', err)
        self.setData({
          categoriesLoading: false,
          availableCategories: [],
          categoryFilters: buildCategoryFilters([], [])
        })
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

  onOpenCategoryPicker: function () {
    var self = this
    var openPicker = function () {
      if (self.data.availableCategories.length === 0) {
        wx.showToast({ title: '暂无可测类别，请先学习内容', icon: 'none' })
        return
      }

      self.setData({
        showCategoryPicker: true,
        selectedCategories: [],
        categoryFilters: buildCategoryFilters(self.data.availableCategories, [])
      })
    }

    if (this.data.categoriesLoading) {
      wx.showToast({ title: '类别加载中，请稍候', icon: 'none' })
      return
    }

    if (this.data.availableCategories.length === 0) {
      this._loadCategories().then(openPicker)
      return
    }

    openPicker()
  },

  onCategoryToggle: function (e) {
    var key = e.currentTarget.dataset.key
    if (!key) return

    var selected = this.data.selectedCategories.slice()
    var idx = selected.indexOf(key)

    if (idx === -1) {
      selected.push(key)
    } else {
      selected.splice(idx, 1)
    }

    this.setData({
      selectedCategories: selected,
      categoryFilters: buildCategoryFilters(this.data.availableCategories, selected)
    })
  },

  onStartThemeQuiz: function () {
    var selected = this.data.selectedCategories
    if (selected.length === 0) {
      wx.showToast({ title: '请至少选择一个类别', icon: 'none' })
      return
    }

    this.setData({ showCategoryPicker: false })

    this._goToQuizPlay({
      mode: 'theme',
      questionCount: 10,
      category: selected.join(','),
      quizMode: 'normal'
    })
  },

  onCloseCategoryPicker: function () {
    this.setData({
      showCategoryPicker: false,
      selectedCategories: [],
      categoryFilters: buildCategoryFilters(this.data.availableCategories, [])
    })
  },

  onMaskTap: function () {
    this.onCloseCategoryPicker()
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
