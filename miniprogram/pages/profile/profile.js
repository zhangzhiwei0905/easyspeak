// pages/profile/profile.js
const api = require('../../utils/api')
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')

function numberOrZero(value) {
  var num = Number(value)
  return isFinite(num) ? num : 0
}

function hasField(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj || {}, key)
}

function buildStreakSubtext(stats) {
  var todayActivity = stats.todayActivity || {}
  var learnSessions = numberOrZero(todayActivity.learn_sessions)
  var reviewItems = numberOrZero(todayActivity.review_items)
  var quizAnswers = numberOrZero(todayActivity.quiz_answers)
  var totalToday = learnSessions + reviewItems + quizAnswers

  if (totalToday > 0) {
    return '今日已完成：学习 ' + learnSessions + ' 次 · 复习 ' + reviewItems + ' 项 · 测验 ' + quizAnswers + ' 题'
  }

  if (stats.activeStreakDays > 0) {
    return '连续保持中，今天完成一次练习即可续上'
  }

  return '今天完成一次学习即可重新开始连续记录'
}

function buildCompactStreakSubtext(stats) {
  var todayActivity = stats.todayActivity || {}
  var learnSessions = numberOrZero(todayActivity.learn_sessions)
  var reviewItems = numberOrZero(todayActivity.review_items)
  var quizAnswers = numberOrZero(todayActivity.quiz_answers)
  var totalToday = learnSessions + reviewItems + quizAnswers

  if (totalToday > 0) {
    return '今日 ' + totalToday + ' 次有效练习'
  }

  if (stats.activeStreakDays > 0) {
    return '今天练一次即可续上'
  }

  return '完成一次即可开始'
}

function normalizeStats(data) {
  data = data || {}
  var activeStreakDays = hasField(data, 'active_streak_days')
    ? numberOrZero(data.active_streak_days)
    : numberOrZero(data.study_streak || data.studyStreak)
  var stats = {
    studyStreak: activeStreakDays,
    activeStreakDays: activeStreakDays,
    legacyStudyStreak: numberOrZero(data.study_streak || data.studyStreak),
    totalPhrases: numberOrZero(data.total_phrases || data.totalPhrases),
    totalWords: numberOrZero(data.total_words || data.totalWords),
    masteredPhrases: numberOrZero(data.mastered_phrases || data.masteredPhrases),
    masteredWords: numberOrZero(data.mastered_words || data.masteredWords),
    totalQuiz: numberOrZero(data.total_quiz || data.totalQuiz),
    avgAccuracy: numberOrZero(data.avg_accuracy || data.avgAccuracy),
    lastActiveDate: data.last_active_date || data.lastActiveDate || '',
    todayActivity: data.today_activity || data.todayActivity || {
      learn_sessions: 0,
      review_items: 0,
      quiz_answers: 0
    },
    streakSources: data.streak_sources || data.streakSources || []
  }
  stats.streakSubtext = buildStreakSubtext(stats)
  stats.streakCompactText = buildCompactStreakSubtext(stats)
  return stats
}

Page({
  data: {
    userInfo: {},
    stats: normalizeStats({}),
    achievements: [],
    achievementGroups: []
  },

  onLoad() {
    this.loadUserInfo()
    this.loadStats()
    this.loadAchievements()
  },

  onShow() {
    this.loadStats()
    this.loadUserInfo()
    this.loadAchievements()
  },

  /**
   * Load user info from cache or app globalData
   */
  loadUserInfo() {
    const app = getApp()
    let userInfo = app.globalData.userInfo || storage.get(storage.KEYS.USER_INFO) || {}

    // If no cached info, try getting WeChat user profile
    if (!userInfo.nickName) {
      userInfo = { nickName: '英语学习者', avatarUrl: '' }
    }

    this.setData({ userInfo: userInfo })
  },

  /**
   * Load stats from API, fallback to local storage
   */
  loadStats() {
    var self = this

    api.get('/review/progress/summary')
      .then(function(data) {
        self.setData({ stats: normalizeStats(data) })
      })
      .catch(function(err) {
        console.warn('[Profile] Failed to load stats from API:', err)
        // Fallback to local data
        self.loadLocalStats()
      })
  },

  /**
   * Load stats from local storage as fallback
   */
  loadLocalStats() {
    var streakDays = storage.getStreakDays() || 0
    var calendar = storage.getStudyCalendar() || []

    var stats = normalizeStats({
      studyStreak: streakDays,
      totalPhrases: 0,
      totalWords: 0,
      totalQuiz: 0,
      avgAccuracy: 0
    })

    // Try to get quiz history for local stats
    var quizHistory = storage.get(storage.KEYS.QUIZ_HISTORY) || []
    if (quizHistory.length > 0) {
      stats.totalQuiz = quizHistory.length
      var correctCount = quizHistory.filter(function(q) { return q.correct }).length
      stats.avgAccuracy = Math.round((correctCount / quizHistory.length) * 100)
      stats.streakSubtext = buildStreakSubtext(stats)
      stats.streakCompactText = buildCompactStreakSubtext(stats)
    }

    this.setData({ stats: stats })
  },

  /**
   * Load achievements from server, fallback to local cache
   */
  loadAchievements() {
    var self = this
    api.get('/user/achievements')
      .then(function(data) {
        var achievements = (data.achievements || []).map(function(a) {
          if (a.unlocked && a.unlocked_at) {
            var d = new Date(a.unlocked_at)
            a.unlocked_at_display = (d.getMonth() + 1) + '月' + d.getDate() + '日'
          }
          return a
        })
        var groups = self._groupAchievements(achievements)
        self.setData({ achievements: achievements, achievementGroups: groups })
        // Cache for offline fallback
        storage.set(storage.KEYS.ACHIEVEMENTS, achievements)
      })
      .catch(function(err) {
        console.warn('[Profile] Failed to load achievements:', err)
        var cached = storage.get(storage.KEYS.ACHIEVEMENTS) || []
        if (cached.length > 0) {
          var groups = self._groupAchievements(cached)
          self.setData({ achievements: cached, achievementGroups: groups })
        }
      })
  },

  /**
   * Group achievements by category for display
   */
  _groupAchievements(achievements) {
    var categoryOrder = ['learning', 'streak', 'word', 'phrase', 'quiz']
    var groupMap = {}
    achievements.forEach(function(item) {
      var cat = item.category || 'other'
      if (!groupMap[cat]) {
        groupMap[cat] = { category: cat, category_zh: item.category_zh || '', items: [] }
      }
      groupMap[cat].items.push(item)
    })
    return categoryOrder.map(function(cat) { return groupMap[cat] }).filter(Boolean)
  },

  /**
   * Navigate to settings page
   */
  goToSettings() {
    wx.navigateTo({
      url: '/pages/settings/settings'
    })
  },

  /**
   * Allow user to update avatar
   */
  onChooseAvatar() {
    var self = this
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: function(res) {
        var tempFilePath = res.tempFiles[0].tempFilePath
        // Update local avatar
        var userInfo = self.data.userInfo
        userInfo.avatarUrl = tempFilePath
        self.setData({ userInfo: userInfo })
        storage.set(storage.KEYS.USER_INFO, userInfo)
        var app = getApp()
        if (app) app.globalData.userInfo = userInfo
        wx.showToast({ title: '头像已更新', icon: 'success' })
      },
      fail: function(err) {
        // User cancelled, ignore
        console.log('[Profile] Avatar selection cancelled')
      }
    })
  }
})
