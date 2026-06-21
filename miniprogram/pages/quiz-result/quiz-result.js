var navigation = require('../../utils/navigation')
var quizType = require('../../utils/quiz-type')

function normalizeResultItem(item) {
  item = item || {}
  var type = item.type || item.question_type || ''
  var options = (item.options || []).map(function (option) {
    return {
      key: option.key || '',
      text: option.text || '',
      isCorrect: !!(option.isCorrect || option.is_correct || option.is_answer)
    }
  })
  var userAnswer = item.userAnswer || item.user_answer || ''
  var correctAnswer = item.correctAnswer || item.correct_answer || ''

  if (!correctAnswer && options.length) {
    var correctOption = options.find(function (option) { return option.isCorrect })
    correctAnswer = correctOption ? correctOption.key + '. ' + correctOption.text : ''
  }

  return Object.assign({}, item, {
    question: item.question || item.prompt || '题目内容暂缺',
    type: type,
    typeLabel: quizType.getQuizTypeMeta(type).label,
    interactionType: item.interactionType || item.interaction_type || 'choice',
    options: options,
    userAnswer: userAnswer || '未作答',
    correctAnswer: correctAnswer || '暂无',
    userAnswerKey: item.userAnswerKey || item.user_answer_key || '',
    isCorrect: !!(item.isCorrect || item.correct),
    explanation: item.explanation || item.hint || ''
  })
}

Page({
  data: {
    correct: 0,
    total: 0,
    accuracy: 0,
    mode: 'random',
    questionCount: 10,
    quizMode: 'normal',
    contentIds: '',

    scorePercent: 0,
    scoreDisplay: 0,
    animating: false,

    performanceEmoji: '🎉',
    performanceText: '太棒了！',

    results: [],
    typeStats: [],

    filter: 'all',
    filteredResults: [],
    displayedResults: [],
    showAll: false,
    visibleCount: 10,
    expandedIndex: -1
  },

  onLoad: function () {
    var app = getApp()
    var quizResult = app.globalData.quizResult

    if (!quizResult) {
      wx.showToast({ title: '无测验结果', icon: 'none' })
      navigation.safeNavigateBack({
        fallbackUrl: '/pages/quiz/quiz',
        fallbackIsTab: true
      })
      return
    }

    var correct = quizResult.correct || 0
    var total = quizResult.total || 0
    var accuracy = total > 0 ? Math.round((correct / total) * 100) : 0

    var performanceEmoji = '📚'
    var performanceText = '多复习一下吧！'
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
    }

    this.setData({
      correct: correct,
      total: total,
      accuracy: accuracy,
      mode: quizResult.mode || 'random',
      questionCount: quizResult.questionCount || total || 10,
      quizMode: quizResult.quizMode || 'normal',
      contentIds: quizResult.contentIds || '',
      performanceEmoji: performanceEmoji,
      performanceText: performanceText,
      results: (quizResult.results || quizResult.details || []).map(normalizeResultItem),
      animating: true
    })

    this._computeTypeStats()
    this._applyFilter()
    this._animateScore(accuracy)
  },

  _animateScore: function (targetPercent) {
    var self = this
    var duration = 1200
    var startTime = Date.now()

    function animate() {
      var elapsed = Date.now() - startTime
      var progress = Math.min(elapsed / duration, 1)
      var eased = 1 - Math.pow(1 - progress, 3)
      var currentPercent = Math.round(targetPercent * eased)

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

  _computeTypeStats: function () {
    var bucket = {}
    this.data.results.forEach(function (item) {
      var type = item.type || 'unknown'
      if (!bucket[type]) {
        bucket[type] = {
          type: type,
          label: quizType.getQuizTypeMeta(type).label,
          correct: 0,
          total: 0
        }
      }

      bucket[type].total += 1
      if (item.isCorrect) {
        bucket[type].correct += 1
      }
    })

    var typeStats = Object.keys(bucket).map(function (type) {
      var stat = bucket[type]
      return {
        type: stat.type,
        label: stat.label,
        correct: stat.correct,
        total: stat.total,
        accuracy: stat.total > 0 ? Math.round((stat.correct / stat.total) * 100) : 0
      }
    })

    this.setData({ typeStats: typeStats })
  },

  _applyFilter: function () {
    var filter = this.data.filter
    var results = this.data.results

    if (filter === 'wrong') {
      results = results.filter(function (item) { return !item.isCorrect })
    } else if (filter !== 'all') {
      results = results.filter(function (item) { return item.type === filter })
    }

    this.setData({
      filteredResults: results,
      displayedResults: results.slice(0, this.data.visibleCount),
      showAll: false,
      expandedIndex: -1
    })
  },

  onFilterTap: function (e) {
    this.setData({ filter: e.currentTarget.dataset.filter })
    this._applyFilter()
  },

  onShowMore: function () {
    this.setData({
      showAll: true,
      displayedResults: this.data.filteredResults
    })
  },

  onRetry: function () {
    var query = [
      'mode=' + encodeURIComponent(this.data.mode),
      'questionCount=' + encodeURIComponent(this.data.questionCount),
      'quizMode=' + encodeURIComponent(this.data.quizMode)
    ]

    if (this.data.contentIds) {
      query.push('contentIds=' + encodeURIComponent(this.data.contentIds))
    }

    wx.redirectTo({
      url: '/pages/quiz-play/quiz-play?' + query.join('&')
    })
  },

  onGoWrongReview: function () {
    var wrongCount = this.data.results.filter(function (item) {
      return !item.isCorrect
    }).length

    if (wrongCount === 0) {
      wx.showToast({ title: '本次没有错题', icon: 'none' })
      return
    }

    wx.redirectTo({
      url: '/pages/quiz-play/quiz-play?mode=wrong_review&questionCount=' + Math.min(wrongCount, 20) + '&quizMode=normal'
    })
  },

  onBackToQuiz: function () {
    wx.switchTab({
      url: '/pages/quiz/quiz'
    })
  },

  onToggleDetail: function (e) {
    var idx = e.currentTarget.dataset.index
    this.setData({
      expandedIndex: this.data.expandedIndex === idx ? -1 : idx
    })
  },

  onShareAppMessage: function () {
    var emoji = this.data.accuracy >= 80 ? '🎉' : this.data.accuracy >= 60 ? '👍' : '💪'
    return {
      title: emoji + ' 我在EasySpeak测验中答对了 ' + this.data.correct + '/' + this.data.total + ' 题！',
      path: '/pages/quiz/quiz'
    }
  }
})
