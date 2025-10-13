# 🔔 SHiFT Bot Notification Guide

## 🤖 **How the Bot Works**

✅ **YES** - The bot does exactly what you want:

1. **Gathers codes** from websites and Reddit
2. **Compares to database** to find truly NEW codes only
3. **Deduplicates** automatically (no duplicate notifications)
4. **Notifies ONLY new codes** that weren't in the database before

## 🚨 **Why You Got Too Many Notifications**

### **Most Likely: First Run**
- If this was your first run, the database was empty
- **ALL codes were "new"** so you got notified about everything
- This is **normal and expected** behavior

### **Other Possibilities:**
- You used "Reset database" option
- Multiple sources found the same codes
- Test mode was enabled

## 🛠️ **How to Control Notifications**

### **Option 1: Use Smart Limits (Recommended)**

The bot now has **automatic spam prevention**:

- **≤5 new codes**: Individual notifications for each
- **>5 new codes**: Single summary notification (prevents spam)
- **Configurable**: You can change the limit

### **Option 2: Manual Control**

When running the workflow manually, you can:

1. **Set notification limit:**
   - `max_notifications: 3` = Max 3 individual notifications
   - `max_notifications: 0` = Always use summary format

2. **Silent mode:**
   - `silent_mode: true` = No notifications, just collect codes

3. **Test mode:**
   - `test_mode: true` = Send test notification only

## 📊 **Expected Behavior Going Forward**

### **Normal Operation (After First Run):**
```
🎮 New SHiFT Code Found!
Code: ABCDE-FGHIJ-KLMNO-PQRST-UVWXY
Reward: Golden Key
Source: Website
```

### **Multiple New Codes (2-5):**
```
🎮 New SHiFT Code Found! (1/3)
Code: ABCDE-FGHIJ-KLMNO-PQRST-UVWXY
...

🎮 New SHiFT Code Found! (2/3)
Code: FGHIJ-KLMNO-PQRST-UVWXY-ZABCD
...
```

### **Many New Codes (>5):**
```
🎮 SHiFT Code Summary (12 codes)
Found 12 codes (likely first run or database reset)

Recent Codes:
• ABCDE-FGHIJ-KLMNO-PQRST-UVWXY - Golden Key
• FGHIJ-KLMNO-PQRST-UVWXY-ZABCD - Diamond Key
• ... and 10 more codes

Note: Individual notifications disabled to prevent spam
```

## ⚙️ **Configuration Options**

### **Environment Variables (Repository Secrets):**
```
MAX_CODES_PER_NOTIFICATION=5    # Default: 5
DISCORD_WEBHOOK_URL=your_url    # Required for Discord
SLACK_WEBHOOK_URL=your_url      # Optional for Slack
HTML_SOURCES=website_urls       # Required: comma-separated
```

### **Workflow Options (Manual Run):**
- **Max notifications:** How many individual notifications before switching to summary
- **Silent mode:** Collect codes but don't notify
- **Test mode:** Send test notification only
- **Reset database:** Start fresh (will cause notification flood)

## 🎯 **Recommended Settings**

### **For Regular Use:**
- `max_notifications: 3` (you'll get max 3 individual notifications)
- `silent_mode: false` (you want notifications)
- `reset_db: false` (keep existing database)

### **For Testing:**
- `test_mode: true` (just test the webhook)
- `silent_mode: true` (don't spam yourself)

### **For First Setup:**
- `max_notifications: 0` (summary only to avoid spam)
- `reset_db: true` (start fresh)

## 🔄 **What Happens Next**

### **Scheduled Runs (Every 30 minutes):**
- Bot checks for new codes
- **Only notifies about truly NEW codes**
- Uses smart limits to prevent spam
- Builds database over time

### **Typical Results:**
- **Most runs:** "No new codes found" (normal!)
- **Occasionally:** 1-2 new codes (when Gearbox releases them)
- **Rarely:** Many codes (special events, first run)

## 🚀 **Quick Actions**

### **To Reduce Notifications:**
1. Set `MAX_CODES_PER_NOTIFICATION=1` in repository secrets
2. Or use `silent_mode: true` for a few runs to build database

### **To Test Without Spam:**
1. Use `test_mode: true` 
2. Or use `max_notifications: 0` (summary only)

### **To Start Fresh:**
1. Use `reset_db: true` once
2. Set `max_notifications: 0` for first run
3. Then use normal settings

The bot is working correctly - it just found a lot of existing codes on the first run! 🎉