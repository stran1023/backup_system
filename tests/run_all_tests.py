#!/usr/bin/env python3
"""
Run all tests for the backup system
"""
import unittest
import sys
import os

def run_all_tests():
    """Run all test suites"""
    # Add parent directory to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    
    # Discover and run all tests
    loader = unittest.TestLoader()
    
    # Import test modules
    from tests.test_storage import TestChunkStorage, TestSnapshotManager
    from tests.test_merkle import TestMerkleTree
    from tests.test_policy import TestPolicyManager
    from tests.test_integration import TestIntegration
    
    # Create test suites
    suites = []
    
    # Storage tests
    storage_suite = unittest.TestSuite()
    storage_suite.addTests(loader.loadTestsFromTestCase(TestChunkStorage))
    storage_suite.addTests(loader.loadTestsFromTestCase(TestSnapshotManager))
    suites.append(("Storage", storage_suite))
    
    # Merkle tests
    merkle_suite = unittest.TestSuite()
    merkle_suite.addTests(loader.loadTestsFromTestCase(TestMerkleTree))
    suites.append(("Merkle", merkle_suite))
    
    # Policy tests
    policy_suite = unittest.TestSuite()
    policy_suite.addTests(loader.loadTestsFromTestCase(TestPolicyManager))
    suites.append(("Policy", policy_suite))
    
    # Integration tests
    integration_suite = unittest.TestSuite()
    integration_suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    suites.append(("Integration", integration_suite))
    
    # Run all suites
    runner = unittest.TextTestRunner(verbosity=2)
    
    print("=" * 60)
    print("Running Backup System Tests")
    print("=" * 60)
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for suite_name, suite in suites:
        print(f"\n{suite_name} Tests:")
        print("-" * 40)
        
        result = runner.run(suite)
        total_tests += result.testsRun
        passed_tests += result.testsRun - len(result.failures) - len(result.errors)
        
        if result.failures:
            for test, traceback in result.failures:
                failed_tests.append(f"{suite_name}.{test}")
        if result.errors:
            for test, traceback in result.errors:
                failed_tests.append(f"{suite_name}.{test}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failed_tests)}")
    
    if failed_tests:
        print("\nFailed tests:")
        for test in failed_tests:
            print(f"  - {test}")
        return False
    else:
        print("\n✓ All tests passed!")
        return True

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)