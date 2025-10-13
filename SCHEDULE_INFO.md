# 📅 Bot Schedule Information

## ⏰ **Current Schedule**

**Your bot runs:** Daily at **7:00 PM Mountain Time**

### **Time Zone Conversion:**
- **Mountain Time (MST/MDT):** 7:00 PM
- **UTC (GitHub Actions):** 1:00 AM (next day)
- **Cron Expression:** `0 1 * * *`

### **Why UTC?**
GitHub Actions uses UTC time, so:
- **Mountain Standard Time (MST):** UTC-7 → 7 PM MST = 2 AM UTC
- **Mountain Daylight Time (MDT):** UTC-6 → 7 PM MDT = 1 AM UTC

*Note: The schedule uses 1 AM UTC to account for daylight saving time changes.*

## 📊 **What Happens Daily**

### **7:00 PM Mountain Time:**
1. 🔍 **Bot searches** all configured sources
2. 🔄 **Compares** found codes to database
3. 📢 **Notifies** only about NEW codes
4. 💾 **Updates** database with any new codes
5. 📈 **Saves** metrics and logs

### **Expected Notifications:**
- **Most days:** "No new codes found" (normal!)
- **Occasionally:** 1-2 new codes when Gearbox releases them
- **Special events:** Multiple codes during promotions

## 🛠️ **Manual Override**

You can always run the bot manually:
1. Go to **Actions** → **"Run SHiFT Bot (Simple)"**
2. Click **"Run workflow"**
3. Choose options if needed
4. Click **"Run workflow"**

## ⚙️ **Schedule Alternatives**

If you want to change the schedule later:

### **Twice Daily:**
```yaml
cron: "0 1,13 * * *"  # 7 PM & 7 AM Mountain Time
```

### **Every 6 Hours:**
```yaml
cron: "0 1,7,13,19 * * *"  # 4 times daily
```

### **Weekdays Only:**
```yaml
cron: "0 1 * * 1-5"  # Monday-Friday at 7 PM Mountain
```

### **Custom Time:**
- **6 PM Mountain:** `cron: "0 0 * * *"`
- **8 PM Mountain:** `cron: "0 2 * * *"`
- **9 PM Mountain:** `cron: "0 3 * * *"`

## 🔍 **Monitoring**

### **Health Monitor:**
Runs every 6 hours to check bot health:
- **6 AM, 12 PM, 6 PM, 12 AM Mountain Time**
- Sends alerts if issues detected

### **How to Check:**
1. **Actions tab:** See all workflow runs
2. **Notifications:** Get Discord/Slack alerts
3. **Artifacts:** Download logs and metrics

## 💡 **Pro Tips**

### **Best Practices:**
- ✅ **Let it run automatically** - no need to manually trigger
- ✅ **Check notifications** - you'll only get alerts for NEW codes
- ✅ **Monitor health** - automatic health checks every 6 hours
- ✅ **Review logs** - check Actions tab if you're curious

### **Troubleshooting:**
- **No notifications:** Normal if no new codes released
- **Failed runs:** Check Actions tab for error details
- **Health alerts:** Bot will notify you if something's wrong

Your bot is now set to run once daily at 7 PM Mountain Time! 🎉