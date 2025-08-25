#!/usr/bin/env python3
"""
Test Concurrent API Calls
=========================
Test multiple simultaneous requests to the OCR endpoint using both PDF files.
"""

import requests
import json
import asyncio
import aiohttp
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def test_concurrent_requests():
    """Test concurrent requests using ThreadPoolExecutor with both PDF files"""
    base_url = "http://localhost:8001"
    
    # Get both PDF files
    test_pdf_dir = Path("test_pdf")
    pdf_files = list(test_pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in test_pdf directory!")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF files:")
    for i, pdf_file in enumerate(pdf_files):
        size_kb = pdf_file.stat().st_size / 1024
        print(f"   {i+1}. {pdf_file.name} ({size_kb:.1f} KB)")
    
    def make_request(request_id):
        """Make a single request using alternating PDF files"""
        # Alternate between PDF files
        pdf_path = pdf_files[request_id % len(pdf_files)]
        start_time = time.time()
        print(f"🚀 Request {request_id} started with {pdf_path.name} at {start_time:.2f}")
        
        try:
            with open(pdf_path, 'rb') as f:
                files = {'file': (pdf_path.name, f, 'application/pdf')}
                response = requests.post(f"{base_url}/ocr", files=files)
            
            end_time = time.time()
            duration = end_time - start_time
            
            if response.status_code == 200:
                result = response.json()
                response_size = len(response.content) / 1024
                print(f"✅ Request {request_id} ({pdf_path.name}) completed in {duration:.2f}s ({response_size:.1f} KB)")
                return {
                    'request_id': request_id,
                    'pdf_file': pdf_path.name,
                    'duration': duration,
                    'status': 'success',
                    'response_size': response_size
                }
            else:
                print(f"❌ Request {request_id} ({pdf_path.name}) failed: {response.status_code}")
                return {
                    'request_id': request_id,
                    'pdf_file': pdf_path.name,
                    'duration': duration,
                    'status': 'failed',
                    'error': response.status_code
                }
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            print(f"❌ Request {request_id} ({pdf_path.name}) error after {duration:.2f}s: {e}")
            return {
                'request_id': request_id,
                'pdf_file': pdf_path.name,
                'duration': duration,
                'status': 'error',
                'error': str(e)
            }
    
    # Test with different numbers of concurrent requests
    for num_concurrent in [2, 4, 8, 12]:
        print(f"\n🧪 Testing {num_concurrent} concurrent requests...")
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(make_request, i+1) for i in range(num_concurrent)]
            results = [future.result() for future in futures]
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful = [r for r in results if r['status'] == 'success']
        failed = [r for r in results if r['status'] != 'success']
        
        if successful:
            avg_duration = sum(r['duration'] for r in successful) / len(successful)
            max_duration = max(r['duration'] for r in successful)
            min_duration = min(r['duration'] for r in successful)
            
            # Group by PDF file
            file_stats = {}
            for result in successful:
                pdf_name = result['pdf_file']
                if pdf_name not in file_stats:
                    file_stats[pdf_name] = []
                file_stats[pdf_name].append(result['duration'])
            
            print(f"📊 Results for {num_concurrent} concurrent requests:")
            print(f"   ✅ Successful: {len(successful)}/{num_concurrent}")
            print(f"   ⏱️ Total time: {total_time:.2f}s")
            print(f"   ⏱️ Avg processing time: {avg_duration:.2f}s")
            print(f"   ⏱️ Min/Max: {min_duration:.2f}s / {max_duration:.2f}s")
            print(f"   🚀 Throughput: {len(successful)/total_time:.2f} requests/second")
            
            # Show stats per file
            for pdf_name, durations in file_stats.items():
                avg_file_duration = sum(durations) / len(durations)
                print(f"   📄 {pdf_name}: {len(durations)} requests, avg {avg_file_duration:.2f}s")
        
        if failed:
            print(f"   ❌ Failed: {len(failed)}")
        
        # Wait a bit between tests
        time.sleep(2)

async def test_async_requests():
    """Test concurrent requests using async/await with both PDF files"""
    base_url = "http://localhost:8001"
    
    # Get both PDF files
    test_pdf_dir = Path("test_pdf")
    pdf_files = list(test_pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in test_pdf directory!")
        return
    
    async def make_async_request(session, request_id):
        """Make a single async request using alternating PDF files"""
        # Alternate between PDF files
        pdf_path = pdf_files[request_id % len(pdf_files)]
        start_time = time.time()
        print(f"🚀 Async Request {request_id} started with {pdf_path.name}")
        
        try:
            # Read file content
            with open(pdf_path, 'rb') as f:
                file_content = f.read()
            
            # Create form data
            data = aiohttp.FormData()
            data.add_field('file', file_content, filename=pdf_path.name, content_type='application/pdf')
            
            async with session.post(f"{base_url}/ocr", data=data) as response:
                end_time = time.time()
                duration = end_time - start_time
                
                if response.status == 200:
                    result = await response.json()
                    response_size = len(await response.read()) / 1024
                    print(f"✅ Async Request {request_id} ({pdf_path.name}) completed in {duration:.2f}s")
                    return {
                        'request_id': request_id, 
                        'pdf_file': pdf_path.name,
                        'duration': duration, 
                        'status': 'success',
                        'response_size': response_size
                    }
                else:
                    print(f"❌ Async Request {request_id} ({pdf_path.name}) failed: {response.status}")
                    return {
                        'request_id': request_id, 
                        'pdf_file': pdf_path.name,
                        'duration': duration, 
                        'status': 'failed'
                    }
        
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            print(f"❌ Async Request {request_id} ({pdf_path.name}) error: {e}")
            return {
                'request_id': request_id, 
                'pdf_file': pdf_path.name,
                'duration': duration, 
                'status': 'error'
            }
    
    print(f"\n🧪 Testing 10 async concurrent requests...")
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = [make_async_request(session, i+1) for i in range(10)]
        results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    successful = [r for r in results if r['status'] == 'success']
    
    print(f"📊 Async Results:")
    print(f"   ✅ Successful: {len(successful)}/10")
    print(f"   ⏱️ Total time: {total_time:.2f}s")
    if successful:
        avg_duration = sum(r['duration'] for r in successful) / len(successful)
        print(f"   ⏱️ Avg processing time: {avg_duration:.2f}s")
        print(f"   🚀 Throughput: {len(successful)/total_time:.2f} requests/second")
        
        # Show stats per file
        file_stats = {}
        for result in successful:
            pdf_name = result['pdf_file']
            if pdf_name not in file_stats:
                file_stats[pdf_name] = []
            file_stats[pdf_name].append(result['duration'])
        
        for pdf_name, durations in file_stats.items():
            avg_file_duration = sum(durations) / len(durations)
            print(f"   📄 {pdf_name}: {len(durations)} requests, avg {avg_file_duration:.2f}s")

if __name__ == "__main__":
    print("🧪 Testing Concurrent API Calls with Multiple PDF Files\n")
    
    # Test synchronous concurrent requests
    test_concurrent_requests()
    
    # Test asynchronous concurrent requests
    # Uncomment the line below if you have aiohttp installed
    # asyncio.run(test_async_requests())
    
    print("\n🎉 Concurrent testing completed!")
