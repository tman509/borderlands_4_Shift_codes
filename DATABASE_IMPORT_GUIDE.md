# 📥 Database Import Guide

## 🎯 **Why Import Your Old Database?**

✅ **Prevents notification spam** - Bot won't notify about codes you already have  
✅ **Preserves history** - Keeps track of all codes you've collected  
✅ **Seamless upgrade** - Continue where you left off  

## 🛠️ **Import Methods**

### **Method 1: Automatic (GitHub Actions) - Recommended**

1. **Go to Actions** → "Import Old Database"
2. **Click "Run workflow"**
3. **Choose options:**
   - ✅ Backup current database
   - Choose source: "From previous workflow run"
4. **Click "Run workflow"**
5. **Wait for completion** - you'll get a notification when done!

### **Method 2: Manual (Local)**

```bash
# Download this repository
git clone your-repo-url
cd your-repo

# Run the import tool
python import_old_database.py path/to/old/shift_codes.db ./shift_codes_new.db

# Replace old with new
mv shift_codes.db shift_codes.backup
mv shift_codes_new.db shift_codes.db
```

### **Method 3: Upload Old Database**

1. **Prepare your old database:**
   - Find your `shift_codes.db` file
   - Zip it: `zip old-database.zip shift_codes.db`

2. **Upload as artifact:**
   - Go to any GitHub Actions run
   - Upload the zip file as "old-database" artifact

3. **Run import workflow:**
   - Actions → "Import Old Database"
   - Choose "Upload as artifact"
   - Run workflow

## 📋 **What Gets Imported**

### **From Old Database:**
- ✅ All shift codes
- ✅ Reward types (golden key, diamond key, etc.)
- ✅ Source information (where code was found)
- ✅ Discovery dates
- ✅ Context information

### **New Features Added:**
- ✅ Normalized codes (better duplicate detection)
- ✅ Activity status tracking
- ✅ Enhanced indexing (faster queries)
- ✅ Migration timestamps

## 🔍 **Import Process Details**

### **What Happens:**
1. **Reads old database** - Extracts all existing codes
2. **Checks for duplicates** - Compares with any existing new database
3. **Normalizes codes** - Improves duplicate detection
4. **Migrates data** - Converts to new schema
5. **Creates indexes** - Optimizes performance
6. **Verifies results** - Ensures data integrity

### **Duplicate Handling:**
- **Smart detection** - Recognizes codes even with different formatting
- **Skips duplicates** - Won't create duplicate entries
- **Reports results** - Shows how many imported vs skipped

## 📊 **Expected Results**

### **Import Summary:**
```
✅ Import completed!
  📥 Imported: 127 codes
  🔄 Duplicates skipped: 3
  ❌ Errors: 0
```

### **Database Statistics:**
```
📊 Database Statistics:
  Total codes: 127
  Active codes: 127
  Recent codes:
    - ABCDE-FGHIJ-KLMNO-PQRST-UVWXY (Golden Key) - 2024-01-15
    - FGHIJ-KLMNO-PQRST-UVWXY-ZABCD (Diamond Key) - 2024-01-14
```

## 🚀 **After Import**

### **What Changes:**
- ✅ **No more spam** - Bot only notifies about NEW codes
- ✅ **Faster performance** - Improved database structure
- ✅ **Better tracking** - Enhanced duplicate detection
- ✅ **Future-proof** - Ready for new features

### **Next Bot Run:**
```
No new codes found. Execution completed in 2.3s
```
*This is what you want to see!*

### **When New Codes Are Released:**
```
🎉 Found 1 new code(s) in 2.1s
  - NEWCO-DE123-45678-90ABC-DEFGH [Golden Key] <- HTML:https://shift.orcicorn.com/
```
*Only truly NEW codes will notify you*

## 🔧 **Troubleshooting**

### **"Old database not found"**
- Check the file path
- Make sure the file is named `shift_codes.db`
- Verify the file isn't corrupted

### **"No codes table found"**
- Your old database might be from a different bot
- Check if it's actually a SHiFT code database
- Try opening it with a SQLite browser

### **"Import failed"**
- Check the error message in the logs
- Ensure you have write permissions
- Try the manual method instead

### **"All codes already exist"**
- This means your databases already had the same codes
- This is actually good - no duplicates!
- The import worked correctly

## 💡 **Pro Tips**

### **Before Import:**
- ✅ **Backup everything** - Keep copies of your old database
- ✅ **Check file size** - Make sure database isn't corrupted
- ✅ **Note code count** - Know how many codes you expect

### **After Import:**
- ✅ **Test a run** - Use silent mode to verify it works
- ✅ **Check notifications** - Should be much quieter now
- ✅ **Monitor logs** - Verify duplicate detection is working

### **Best Practices:**
- 🔄 **Regular backups** - GitHub Actions automatically backs up
- 📊 **Monitor metrics** - Check execution times and code counts
- 🔍 **Review logs** - Ensure everything is working smoothly

## 🎯 **Quick Start**

**Just want to import quickly?**

1. Go to **Actions** → **"Import Old Database"**
2. Click **"Run workflow"**
3. Keep default settings
4. Click **"Run workflow"**
5. Wait for completion notification
6. Enjoy spam-free notifications! 🎉

Your old codes are preserved, and you'll only get notified about genuinely new codes going forward!