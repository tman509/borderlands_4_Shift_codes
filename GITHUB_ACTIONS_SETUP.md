# 🚀 GitHub Actions Setup Guide

This guide will help you set up the improved Borderlands 4 SHiFT Code Bot to run automatically on GitHub Actions.

## 📋 Prerequisites

1. A GitHub repository with the bot code
2. Discord and/or Slack webhook URLs for notifications
3. (Optional) Reddit API credentials

## 🔧 Setup Steps

### 1. Configure Repository Secrets

Go to your repository → Settings → Secrets and variables → Actions, then add these secrets:

#### Required Secrets
```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN
```

#### Optional Secrets
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
HTML_SOURCES=https://shift.orcicorn.com/,https://mentalmars.com/game-news/borderlands-3-golden-keys/
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=borderlands4-shift-bot/1.0
REDDIT_SUBS=shiftcodes,Borderlands,borderlands3
REDEEM_URL=https://shift.gearboxsoftware.com/rewards
```

### 2. Enable GitHub Actions

1. Go to your repository → Actions tab
2. If prompted, click "I understand my workflows and want to enable them"
3. The workflows will now be active

### 3. Available Workflows

#### 🤖 `run_improved.yml` - Main Bot Execution
- **Schedule:** Every 30 minutes
- **Manual trigger:** Available with options
- **Features:**
  - Health check before running
  - Database migration
  - Test notifications
  - Failure alerts
  - Comprehensive logging

#### 🧪 `ci_improved.yml` - Continuous Integration
- **Triggers:** Push to main/develop, Pull requests
- **Features:**
  - Multi-Python version testing
  - Code formatting checks
  - Security scanning
  - Cross-platform compatibility
  - Comprehensive testing

#### 📊 `monitor.yml` - Health Monitoring
- **Schedule:** Every 6 hours
- **Features:**
  - Comprehensive health checks
  - Activity monitoring
  - Automated alerts
  - Detailed reporting

## 🎮 Manual Workflow Triggers

### Running the Bot Manually

1. Go to Actions → "Run SHiFT Bot (Improved)"
2. Click "Run workflow"
3. Choose options:
   - **Reset DB:** Start with fresh database
   - **Test webhook:** Send test notifications
   - **Health check only:** Just check system health

### Testing Notifications

1. Go to Actions → "Run SHiFT Bot (Improved)"
2. Click "Run workflow"
3. Enable "Send test notifications"
4. Add custom test message
5. Click "Run workflow"

## 📊 Monitoring & Alerts

### Automatic Health Monitoring

The monitor workflow runs every 6 hours and:
- ✅ Checks database connectivity
- 🌐 Verifies network access
- ⚙️ Validates configuration
- 📈 Monitors bot activity
- 🚨 Sends alerts if issues detected

### Alert Conditions

Alerts are sent when:
- Health check fails (critical)
- No codes found for 7+ days (warning)
- Database issues detected
- Configuration problems found

### Viewing Results

1. **GitHub Actions Tab:** See all workflow runs
2. **Artifacts:** Download logs, metrics, and reports
3. **Job Summaries:** Quick overview in GitHub interface
4. **Discord/Slack:** Real-time notifications

## 🔍 Troubleshooting

### Common Issues

#### "No sources configured" Error
- **Cause:** Missing HTML_SOURCES or Reddit credentials
- **Fix:** Add at least one source in repository secrets

#### Webhook Notifications Not Working
- **Cause:** Invalid webhook URLs
- **Fix:** Verify webhook URLs in secrets, test with manual trigger

#### Database Errors
- **Cause:** Corrupted database or schema issues
- **Fix:** Use "Reset DB" option in manual workflow trigger

#### Health Check Failures
- **Cause:** Network issues or configuration problems
- **Fix:** Check the health check logs for specific error details

### Debug Steps

1. **Check Workflow Logs:**
   - Go to Actions → Select failed run → View logs

2. **Run Health Check:**
   - Manually trigger monitor workflow
   - Review health check results

3. **Test Configuration:**
   - Use manual workflow with test notifications
   - Verify all secrets are set correctly

4. **Reset and Retry:**
   - Use "Reset DB" option
   - Check if issue persists

## 📈 Performance Optimization

### Adjusting Schedule

Edit `.github/workflows/run_improved.yml`:
```yaml
schedule:
  - cron: "*/15 * * * *"  # Every 15 minutes (more frequent)
  - cron: "0 */2 * * *"   # Every 2 hours (less frequent)
```

### Resource Usage

- **Database:** Stored as GitHub Actions artifacts (30-day retention)
- **Logs:** Separate artifacts with 7-day retention
- **Metrics:** JSON files for monitoring trends

### Cost Considerations

GitHub Actions is free for public repositories with generous limits:
- 2,000 minutes/month for private repos
- Unlimited for public repos
- Each bot run takes ~2-3 minutes

## 🔒 Security Best Practices

### Secrets Management
- ✅ Use repository secrets for sensitive data
- ✅ Never commit webhook URLs or API keys
- ✅ Regularly rotate API credentials
- ✅ Use least-privilege access

### Monitoring
- 📊 Review workflow logs regularly
- 🚨 Set up failure notifications
- 🔍 Monitor for unusual activity
- 📈 Track performance metrics

## 🆘 Support

### Getting Help

1. **Check Logs:** Always start with GitHub Actions logs
2. **Health Check:** Run the monitor workflow
3. **Test Configuration:** Use manual triggers with test options
4. **Review Documentation:** Check README_improved.md

### Reporting Issues

When reporting issues, include:
- Workflow run URL
- Error messages from logs
- Configuration (without sensitive data)
- Steps to reproduce

## 🎯 Next Steps

1. ✅ Set up repository secrets
2. ✅ Enable workflows
3. ✅ Test with manual trigger
4. ✅ Verify notifications work
5. ✅ Monitor for a few days
6. ✅ Adjust schedule if needed

Your bot is now ready to run automatically on GitHub Actions with improved reliability, monitoring, and alerting! 🎉