import ee

print("=" * 60)
print("Google Earth Engine Setup")
print("=" * 60)
print("\nStep 1: Authenticate with Google")
print("This will open a browser window for you to sign in.")
print("\nPress Enter to continue...")
input()

try:
    ee.Authenticate()
    print("\n✓ Authentication successful!")
except Exception as e:
    print(f"\n✗ Authentication error: {e}")
    exit(1)

print("\n" + "=" * 60)
print("Step 2: Set up your Cloud Project")
print("=" * 60)
print("\nYou need a Google Cloud project ID.")
print("\nIf you don't have one:")
print("  1. Visit: https://console.cloud.google.com/")
print("  2. Create a new project (or use existing)")
print("  3. Copy the Project ID")
print("\nEnter your Google Cloud Project ID: ", end="")
project_id = input().strip()

if not project_id:
    print("✗ No project ID provided. Exiting.")
    exit(1)

try:
    print(f"\nInitializing Earth Engine with project: {project_id}")
    ee.Initialize(project=project_id)
    print("✓ Earth Engine is ready to use!")
    
    # Save to .env file
    with open('.env', 'a') as f:
        f.write(f"\nGEE_PROJECT_ID={project_id}\n")
    print(f"\n✓ Project ID saved to .env file")
    
except Exception as e:
    print(f"\n✗ Initialization error: {e}")
    print("\nMake sure:")
    print("  1. The project ID is correct")
    print("  2. Earth Engine API is enabled for this project")
    print("  3. Visit: https://console.cloud.google.com/apis/library/earthengine.googleapis.com")
    exit(1)
