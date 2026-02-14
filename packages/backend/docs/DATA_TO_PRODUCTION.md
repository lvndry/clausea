# Data Promotion Guide

This guide explains how to use the promotion functionality to transfer data from your local MongoDB database to production.

## Overview

The promotion system allows you to:

- View a summary of data in both local and production databases
- Perform dry runs to see what would be promoted
- Execute actual promotions with safety checks
- Promote specific data types (products, documents, product overviews)

## Prerequisites

1. **Environment Variables**: Make sure you have both database URIs configured:

   - `MONGO_URI`: Your local MongoDB connection string
   - `PRODUCTION_MONGO_URI`: Your production MongoDB connection string

2. **Streamlit Secrets (Optional)**: For convenience, you can create a secrets file:

   ```bash
   # Create the .streamlit directory
   mkdir -p .streamlit

   # Copy the template and edit it
   cp .streamlit/secrets.toml .streamlit/secrets.toml
   ```

   Then edit `.streamlit/secrets.toml` with your database URIs and API URL:

   ```toml
   MONGO_URI = "mongodb://localhost:27017/clausea"
   PRODUCTION_MONGO_URI = "mongodb+srv://username:password@cluster.mongodb.net/clausea"
   API_BASE_URL = "http://localhost:8000"
   ```

3. **API Server**: The Clausea API server must be running, as the Streamlit dashboard makes HTTP requests to promotion endpoints. Start it with:

   ```bash
   # From the backend directory
   uvicorn main:app --reload
   ```

   The default API URL is `http://localhost:8000` (configurable in the dashboard interface).

4. **Dependencies**: Install the required dependencies:
   ```bash
   uv sync
   ```

## Running the Promotion Dashboard

1. **Start the Streamlit Dashboard**:

   ```bash
   streamlit run src/dashboard/app.py
   ```

2. **Navigate to Promotion**: In the dashboard sidebar, select "Promotion"

## Using the Promotion Interface

### 1. Configuration

- **Local Database URI**: Your local MongoDB connection string
- **Production Database URI**: Your production MongoDB connection string
- **API Base URL**: The URL where your Clausea API is running (default: http://localhost:8000)

**Note**: If you've set up the `.streamlit/secrets.toml` file, these fields will be pre-populated with your configuration. Otherwise, you'll need to enter them manually each time.

### 2. Promotion Summary

Click "Get Promotion Summary" to see:

- Number of products, documents, and product overviews in both databases
- Detailed breakdown of what data exists where

### 3. Dry Run

Before performing actual promotions, always run a dry run to:

- See what data would be promoted
- Identify any potential issues
- Verify the promotion plan

Available dry run options:

- **All Data**: Complete promotion simulation
- **Products Only**: Only product data
- **Documents Only**: Only document data

### 4. Execute Promotion

⚠️ **Warning**: This will actually modify your production database!

1. **Confirm**: Check the confirmation checkbox
2. **Choose Promotion Type**:
   - **All Data**: Complete promotion
   - **Products Only**: Only product data
   - **Documents Only**: Only document data

## Promotion Behavior

### Data Safety

- **Duplicate Prevention**: The system checks for existing records and skips duplicates
- **Error Handling**: Failed promotions are logged and reported
- **Dry Run Mode**: Always test with dry runs first

### What Gets Promoted

- **Products**: Product information, domains, categories
- **Documents**: Document content, metadata, analysis
- **Product Overviews**: Product-level overview payloads derived from analyzed documents

### Promotion Process

1. **Connection**: Establishes connections to both databases
2. **Validation**: Checks data integrity
3. **Promotion**: Transfers data with duplicate checking
4. **Reporting**: Provides detailed results and error logs

## API Endpoints

The promotion system provides use `/promotion`router (packages/backend/src/dashboard/components/promotion.py)

## Troubleshooting

### Common Issues

1. **Connection Errors**:

   - Verify MongoDB URIs are correct
   - Check network connectivity
   - Ensure MongoDB instances are running

2. **Permission Errors**:

   - Verify database user permissions
   - Check if production database allows writes

3. **API Connection Issues**:
   - Ensure the Clausea API server is running
   - Check the API Base URL configuration
   - Verify CORS settings if accessing from different domains

### Error Handling

- All errors are logged and displayed in the interface
- Failed promotions don't affect successfully promoted data
- Check the promotion results for detailed error information

## Best Practices

1. **Always Backup**: Create a backup of your production database before promotion
2. **Test First**: Always run dry runs before actual promotions
3. **Monitor**: Watch the promotion progress and check results
4. **Verify**: After promotion, verify data integrity in production
5. **Document**: Keep records of what was promoted and when

## Security Considerations

- Database URIs contain sensitive credentials - keep them secure
- Production database access should be restricted
- Consider using environment variables for sensitive configuration
- Monitor promotion logs for any security-related issues

## Support

If you encounter issues:

1. Check the error logs in the promotion interface
2. Verify your database connections
3. Ensure all prerequisites are met
4. Review the promotion results for specific error details
