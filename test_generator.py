from pathlib import Path
from typing import List
import typer
from phi.llm.google import Gemini
from phi.assistant import Assistant
import time
import os

app = typer.Typer()

TEST_TEMPLATE = '''using System;
using System.Threading.Tasks;
using Xunit;
using Moq;
using FluentAssertions;
using Microsoft.Extensions.Logging;
using System.Collections.Generic;
using System.Linq;

namespace YourProject.Tests
{
    public class ExampleServiceTests
    {
        private readonly Mock<IExampleRepository> _mockRepository;
        private readonly Mock<ILogger<ExampleService>> _mockLogger;
        private readonly ExampleService _service;

        public ExampleServiceTests()
        {
            _mockRepository = new Mock<IExampleRepository>();
            _mockLogger = new Mock<ILogger<ExampleService>>();
            _service = new ExampleService(_mockRepository.Object, _mockLogger.Object);
        }

        [Fact]
        public async Task GetById_WhenItemExists_ReturnsItem()
        {
            // Arrange
            var expectedItem = new ExampleItem { Id = 1, Name = "Test" };
            _mockRepository
                .Setup(repo => repo.GetByIdAsync(1))
                .ReturnsAsync(expectedItem);

            // Act
            var result = await _service.GetByIdAsync(1);

            // Assert
            result.Should().NotBeNull();
            result.Should().BeEquivalentTo(expectedItem);
            _mockRepository.Verify(repo => repo.GetByIdAsync(1), Times.Once);
        }

        [Fact]
        public async Task GetById_WhenItemDoesNotExist_ReturnsNull()
        {
            // Arrange
            _mockRepository
                .Setup(repo => repo.GetByIdAsync(1))
                .ReturnsAsync((ExampleItem)null);

            // Act
            var result = await _service.GetByIdAsync(1);

            // Assert
            result.Should().BeNull();
            _mockRepository.Verify(repo => repo.GetByIdAsync(1), Times.Once);
        }
    }
}'''

class CSharpTestGenerator:
    def __init__(self):
        os.environ["GOOGLE_API_KEY"] = "AIzaSyB8iyOtxVwEiiND1q--Zbp9Nfl9b8NmS7k"
        self.assistant = Assistant(
            name="C# Test Generator",
            llm=Gemini(),  # Varsayılan ayarları kullan
            description="C# unit test generator that creates xUnit tests",
            instructions=[
                "You are a C# test generator that creates complete and detailed unit tests",
                "Always include full implementation, not just namespaces or class definitions",
                "Generate full test methods with Arrange, Act, Assert sections",
                "Include all necessary mock setups and verifications",
                "Use FluentAssertions for assertions",
                "Follow the exact template structure provided"
            ]
        )
        
    def find_cs_files(self, source_path: Path) -> List[Path]:
        """Verilen dizindeki tüm .cs dosyalarını bulur."""
        cs_files = []
        for file_path in source_path.rglob("*.cs"):
            if file_path.is_file() and "Tests" not in str(file_path):
                cs_files.append(file_path)
        return cs_files

    def generate_tests(self, source_path: str):
        """Her C# dosyası için unit testler oluşturur."""
        path = Path(source_path)
        cs_files = self.find_cs_files(path)
        
        for cs_file in cs_files:
            print(f"\nGenerating tests for: {cs_file}")
            
            # Dosya içeriğini oku
            with open(cs_file, 'r', encoding='utf-8') as f:
                code_content = f.read()
            
            print("File content length:", len(code_content))

            # Test dosyası adını oluştur
            test_file_name = f"{cs_file.stem}Tests.cs"
            test_file_path = cs_file.parent / "Tests" / test_file_name

            # AI'dan test kodu oluşturmasını iste
            print("Requesting AI to generate tests...")
            start_time = time.time()
            
            try:
                prompt = f"""IMPORTANT: Generate a COMPLETE C# test file with FULL implementation, not just namespaces or class definitions.

Here's the template to follow EXACTLY:

{TEST_TEMPLATE}

Now, analyze this C# code and create similar COMPLETE tests with FULL implementation:

{code_content}

REQUIREMENTS:
1. Include ALL using statements at the top
2. Create proper namespace: LMS.Service.Tests
3. Create test class with constructor and private fields
4. Implement COMPLETE test methods for ALL public methods
5. Each test method MUST have:
   - Arrange section with mock setups
   - Act section calling the method
   - Assert section with FluentAssertions
6. Follow naming: MethodName_Scenario_ExpectedResult
7. Include ALL necessary mock objects
8. Tests MUST be COMPLETE and RUNNABLE

DO NOT skip any implementation details. Generate FULL and COMPLETE test code.
Respond with ONLY the C# test code, no explanations or additional text."""

                response = ""
                for message in self.assistant.run(prompt):
                    response += str(message)
                
                print(f"Generation took {time.time() - start_time:.2f} seconds")
                
                if not response:
                    print("Warning: Empty response received")
                    continue
                    
                test_code = response
                
                # Yanıt kontrolü
                if len(test_code.strip()) < 100:
                    print("Warning: Response too short, skipping...")
                    continue

                if "public class" not in test_code or "[Fact]" not in test_code:
                    print("Warning: Response doesn't contain required test elements, skipping...")
                    continue

                # Test dizinini oluştur
                test_file_path.parent.mkdir(parents=True, exist_ok=True)

                # Test kodunu kaydet
                with open(test_file_path, 'w', encoding='utf-8') as f:
                    f.write(test_code)

                print(f"Tests saved to: {test_file_path}")
                print("Test content preview:")
                print("=" * 50)
                print(test_code[:500] + "...")
                print("=" * 50)
            
            except Exception as e:
                print(f"Error during test generation: {str(e)}")
                continue

@app.command()
def main(source_path: str):
    """C# projesindeki dosyalar için unit testler oluşturur."""
    generator = CSharpTestGenerator()
    generator.generate_tests(source_path)

if __name__ == "__main__":
    app() 