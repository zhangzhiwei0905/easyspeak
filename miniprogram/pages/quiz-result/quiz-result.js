/**
 * EasySpeak - Quiz Result Page (答题结果)
 * Shows score circle animation, question review list, and action buttons
 */

Page({
  data: {
    // Result data
    correct: 0,
    total: 0,
    accuracy: 0,
    quizType: 'lightning',

    // Score circle animation
    scorePercent: 0,
    scoreDisplay: 0,
    animating: false,

    // Performance message
    performanceEmoji: '🎉',
    performanceText: '太棒了！',

    // Question review list
    results: [],

    // Breakdown by type
    typeStats: [],

    // Filter
    filter: 'all', // all | wrong | phrase_meaning | word_phonetic | fill_blank
    filteredResults: [],

    // UI
    showAll: false,
    visibleCount: 5
  },

  onLoad: function () {
    var app = getApp()
    var quizResult = app.globalData.quizResult

    if (!quizResult) {
      // No result data, go back
      wx.showToast({ title: '无测验结果', icon: 'none' })
      wx.navigateBack()
      return
    }

    var correct = quizResult.correct || 0
    var total = quizResult.total || 0
    var accuracy = total > 0 ? Math.round((correct / total) * 100) : 0

    // Performance evaluation
    var performanceEmoji = '🎉'
    var performanceText = '太棒了！'
    if (accuracy === 100) {
      performanceEmoji = '🏆'
      performanceText = '完美满分！'
    } else if (accuracy >= 80) {
      performanceEmoji = '🎉'
      performanceText = '非常优秀！'
    } else if (accuracy >= 60) {
      performanceEmoji = '👍'
      performanceText = '继续加油！'
    } else if (accuracy >= 40) {
      performanceEmoji = '💪'
      performanceText = '还需努力！'
    } else {
      performanceEmoji = '📚'
      performanceText = '多复习一下吧！'
    }

    this.setData({
      correct: correct,
      total: total,
      accuracy: accuracy,
      quizType: quizResult.quizType || 'lightning',
      performanceEmoji: performanceEmoji,
      performanceText: performanceText,
      results: quizResult.results || [],
      animating: true
    })

    // Compute breakdown by type
    this._computeTypeStats()
    this._applyFilter()

    // Trigger score animation
    this._animateScore(accuracy)
  },

  // ========================
  // Score Animation
  // ========================

  _animateScore: function (targetPercent) {
    var self = this
    var duration = 1200
    var startTime = Date.now()

    var animate = function () {
      var elapsed = Date.now() - startTime
      var progress = Math.min(elapsed / duration, 1)

      // Ease out cubic
      var eased = 1 - Math.pow(1 - progress, 3)
      var currentPercent = Math.round(targetPercent * eased)
      var currentScore = Math.round((self.data.correct / Math.max(self.data.total, 1)) * eased * 100) / 100

      self.setData({
        scorePercent: currentPercent,
        scoreDisplay: Math.min(Math.round(self.data.correct * eased), self.data.correct)
      })

      if (progress < 1) {
        setTimeout(animate, 16)
      } else {
        self.setData({
          scorePercent: targetPercent,
          scoreDisplay: self.data.correct,
          animating: false
        })
      }
    }

    setTimeout(animate, 300)
  },

  // ========================
  // Type Stats & Filter
  // ========================

  _computeTypeStats: function () {
    var results = this.data.results
    var typeMap = {
      'phrase_meaning': { label: '短语含义', correct: 0, total: 0 },
      'word_phonetic': { label: '单词音标', correct: 0, total: 0 },
      'fill_blank': { label: '填空题', correct: 0, total: 0 }
    }

    results.forEach(function (r) {
      var t = r.type || 'phrase_meaning'
      if (!typeMap[t]) {
        typeMap[t] = { label: t, correct: 0, total: 0 }
      }
      typeMap[t].total += 1
      if (r.isCorrect) typeMap[t].correct += 1
    })

    var typeStats = Object.keys(typeMap)
      .filter(function (k) { return typeMap[k].total > 0 })
      .map(function (k) {
        var s = typeMap[k]
        return {
          type: k,
          label: s.label,
          correct: s.correct,
          total: s.total,
          accuracy: s.total > 0 ? Math.round((s.correct / s.total) * 100) : 0
        }
      })

    this.setData({ typeStats: typeStats })
  },

  _applyFilter: function () {
    var filter = this.data.filter
    var results = this.data.results

    var filtered = results
    if (filter === 'wrong') {
      filtered = results.filter(function (r) { return !r.isCorrect })
    } else if (filter !== 'all') {
      filtered = results.filter(function (r) { return r.type === filter })
    }

    this.setData({ filteredResults: filtered, showAll: false })
  },

  onFilterTap: function (e) {
    var filter = e.currentTarget.dataset.filter
    this.setData({ filter: filter })
    this._applyFilter()
  },

  // ========================
  // Actions
  // ========================

  onShowMore: function () {
    this.setData({ showAll: true })
  },

  onRetry: function () {
    var type = this.data.quizType || 'lightning'
    var count = this.data.total || 10
    var url = '/pages/quiz-play/quiz-play?type=' + type + '&count=' + count

    if (type === 'theme') {
      url += '&mode=normal'
    } else if (type === 'lightning') {
      url += '&mode=timed'
    } else {
      url += '&mode=normal'
    }

    wx.redirectTo({ url: url })
  },

  onBackToQuiz: function () {
    wx.navigateBack({ delta: 2 })
  },

  onShareAppMessage: function () {
    var accuracy = this.data.accuracy
    var emoji = accuracy >= 80 ? '🎉' : accuracy >= 60 ? '👍' : '💪'
    return {
      title: emoji + ' 我在EasySpeak测验中答对了 ' + this.data.correct + '/' + this.data.total + ' 题！',
      path: '/pages/quiz/quiz'
    }
  }
})
