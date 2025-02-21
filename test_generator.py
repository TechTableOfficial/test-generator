from pathlib import Path
from typing import List
import typer
import google.generativeai as genai
from phi.assistant import Assistant
from phi.llm.google import Gemini
from phi.llm.ollama import Ollama
from phi.model.mistral import MistralChat
import time
import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk
import subprocess
import json
import re
import uuid
import requests
from phi.agent import Agent, RunResponse
from langchain_core.prompts import ChatPromptTemplate
from langchain_mistralai import ChatMistralAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import SystemMessage, HumanMessage

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
            _mockRepository.Verify(repo => repo.GetById_WhenItemDoesNotExist_ReturnsNull(), Times.Once);
        }
    }
}'''

class TestGeneratorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("C# Test Generator ve Analizör")
        self.root.geometry("800x600")
        
        # Ana container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Grid yapılandırması
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # API Key girişi
        ttk.Label(main_frame, text="Gemini API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(main_frame, textvariable=self.api_key_var, width=50)
        self.api_key_entry.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Proje yolu seçimi
        ttk.Label(main_frame, text="Proje Yolu:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.project_path_var = tk.StringVar()
        path_frame = ttk.Frame(main_frame)
        path_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        path_frame.columnconfigure(0, weight=1)
        
        self.path_entry = ttk.Entry(path_frame, textvariable=self.project_path_var)
        self.path_entry.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        self.browse_button = ttk.Button(path_frame, text="Gözat", command=self.browse_directory)
        self.browse_button.grid(row=0, column=1, padx=5)
        
        # Solution seçimi için ComboBox
        self.solution_var = tk.StringVar()
        self.solution_combo = ttk.Combobox(main_frame, textvariable=self.solution_var, state="readonly")
        self.solution_combo.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)
        self.solution_combo.grid_remove()  # Başlangıçta gizli
        
        # Test oluşturma butonu
        self.generate_button = ttk.Button(main_frame, text="Testleri Oluştur ve Çalıştır", command=self.generate_and_run_tests)
        self.generate_button.grid(row=5, column=0, pady=20)
        
        # Log alanı
        log_frame = ttk.LabelFrame(main_frame, text="Test Sonuçları ve Analiz", padding="5")
        log_frame.grid(row=6, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=7, column=0, sticky=(tk.W, tk.E), pady=10)
        
    def log_message(self, message: str, level: str = "info"):
        tags = {
            "info": "",
            "success": "success",
            "error": "error",
            "warning": "warning"
        }
        
        self.log_text.tag_configure("success", foreground="green")
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("warning", foreground="orange")
        
        self.log_text.insert(tk.END, f"{message}\n", tags[level])
        self.log_text.see(tk.END)
        self.root.update()
        
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.project_path_var.set(directory)
            
    def generate_and_run_tests(self):
        api_key = self.api_key_var.get().strip()
        project_path = self.project_path_var.get().strip()
        
        # ----------------------------------------
        #if not api_key:
        #    messagebox.showerror("Hata", "Lütfen Gemini API Key giriniz!")
        #    return
        # ----------------------------------------
            
        if not project_path:
            messagebox.showerror("Hata", "Lütfen proje yolunu seçiniz!")
            return
        
        self.log_text.delete(1.0, tk.END)
        self.progress.start()
        self.generate_button.state(['disabled'])
        
        try:
            generator = CSharpTestGenerator(api_key)
            test_results = generator.generate_and_run_tests(project_path, self.log_message)
            
            if test_results:
                self.analyze_test_results(test_results, generator)
            
        except Exception as e:
            self.log_message(f"Hata oluştu: {str(e)}", "error")
        finally:
            self.progress.stop()
            self.generate_button.state(['!disabled'])
            
    def analyze_test_results(self, test_results: dict, generator: 'CSharpTestGenerator'):
        for test_file, result in test_results.items():
            if result.get("error"):
                self.log_message(f"\nTest dosyası analizi: {test_file}", "warning")
                generator.analyze_test_error(test_file, result["error"], self.log_message)

    def update_solution_list(self, solutions):
        """Solution listesini günceller ve ComboBox'ı gösterir."""
        if solutions:
            self.solution_combo.grid()  # ComboBox'ı göster
            self.solution_combo['values'] = [str(s) for s in solutions]
            self.solution_combo.set(solutions[0])  # İlk solution'ı seç
        else:
            self.solution_combo.grid_remove()  # ComboBox'ı gizle

class OllamaAPI:
    def __init__(self, base_url="http://localhost:11434"):
        self.base_url = base_url
        
    def generate(self, prompt: str, model: str = "qwen2.5-coder:latest") -> str:
        """Ollama API'sini kullanarak yanıt üretir."""
        url = f"{self.base_url}/api/generate"
        
        data = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            result = response.json()
            return result.get('response', '')
        except Exception as e:
            print(f"Ollama API hatası: {str(e)}")
            return ""

class CSharpTestGenerator:
    def __init__(self, api_key=None):
        # Mistral modelini yapılandır
        self.llm = ChatMistralAI(
            api_key=api_key,
            model="mistral-large-latest",
            temperature=0.7,
            max_tokens=4096,
            top_p=0.95
        )
        
        # Test Generator için sistem mesajı
        self.test_generator_system = SystemMessage(
            content="You are a C# test generator that creates and analyzes unit tests. "
            "Create complete test implementations with all necessary components. "
            "Focus on both syntax errors and logical issues. "
            "Provide clear, actionable suggestions for improvements. "
            "NEVER use markdown code blocks (```) in your response. "
            "NEVER include any explanations or comments in your response. "
            "Return ONLY pure C# code without any formatting or markdown."
        )
        
        # Test Analyzer için sistem mesajı
        self.analyzer_system = SystemMessage(
            content="You are a C# test analyzer that analyzes test failures. "
            "Analyze build errors and test failures. "
            "Provide specific recommendations to fix issues. "
            "Focus on root causes and actionable solutions. "
            "Explain expected vs actual behavior for failures."
        )

    def run_llm(self, prompt: str, is_analyzer: bool = False) -> str:
        """LLM'i çalıştırır ve yanıt alır."""
        try:
            # Sistem mesajını seç
            system_message = self.analyzer_system if is_analyzer else self.test_generator_system
            
            # Mesajları oluştur
            messages = [
                system_message,
                HumanMessage(content=prompt)
            ]
            
            # LLM'den yanıt al
            response = self.llm.invoke(messages)
            
            # Backtick karakterlerini temizle ve kodu düzelt
            content = str(response.content)
            content = re.sub(r'^```csharp\s*', '', content)  # Başlangıç kod bloğunu temizle
            content = re.sub(r'\s*```$', '', content)        # Bitiş kod bloğunu temizle
            content = re.sub(r'```\s*$', '', content)        # Alternatif bitiş bloğunu temizle
            content = content.replace('`', '')               # Tek tırnak işaretlerini temizle
            content = '\n'.join(line.rstrip() for line in content.splitlines() if line.strip())
            
            return content
            
        except Exception as e:
            print(f"LLM hatası: {str(e)}")
            return ""

    def find_solution_file(self, start_path: Path) -> Path:
        """Verilen dizinden başlayarak üst dizinlerde .sln dosyalarını arar."""
        solutions = []
        current_path = start_path
        
        # Önce mevcut dizinde ara
        sln_files = list(current_path.glob("*.sln"))
        solutions.extend(sln_files)
        
        # Üst dizinlerde ara
        while current_path != current_path.parent:
            current_path = current_path.parent
            sln_files = list(current_path.glob("*.sln"))
            solutions.extend(sln_files)
        
        if not solutions:
            raise FileNotFoundError(f"Bu dizinde veya üst dizinlerde .sln dosyası bulunamadı: {start_path}")
        
        # Eğer birden fazla solution varsa, GUI'den seçim yap
        if len(solutions) > 1:
            app = self.root if hasattr(self, 'root') else None
            if app and hasattr(app, 'update_solution_list'):
                app.update_solution_list(solutions)
                selected = app.solution_var.get()
                return Path(selected) if selected else solutions[0]
        
        return solutions[0]

    def find_cs_files(self, source_path: Path) -> List[Path]:
        """Verilen dizindeki tüm .cs dosyalarını bulur."""
        cs_files = []
        for file_path in source_path.rglob("*.cs"):
            if file_path.is_file() and "Tests" not in str(file_path):
                cs_files.append(file_path)
        return cs_files

    def find_csproj_files(self, source_path: Path) -> List[Path]:
        """Solution dizinindeki tüm .csproj dosyalarını bulur."""
        csproj_files = []
        for file_path in source_path.rglob("*.csproj"):
            if file_path.is_file() and "Tests" not in str(file_path):
                csproj_files.append(file_path)
        return csproj_files

    def add_project_to_solution(self, solution_path: Path, project_path: Path, log_callback) -> bool:
        """Test projesini solution dosyasına ekler."""
        try:
            # Solution dosyasını oku
            with open(solution_path, 'r', encoding='utf-8') as f:
                solution_content = f.read()
            
            # Proje adını ve yolunu kontrol et
            project_name = "Tests"  # Sabit proje adı
            csproj_path = project_path / "Tests.csproj"
            
            # Eğer proje zaten solution'da varsa, ekleme
            if f'"{project_name}"' in solution_content:
                log_callback(f"Proje zaten solution'da mevcut: {project_name}", "warning")
                return True
            
            # Proje GUID'ini oluştur
            project_guid = '{' + str(uuid.uuid4()).upper() + '}'
            vs_guid = "9A19103F-16F7-4668-BE54-9A1E7A4F7556"  # .NET Core/Standard projesi için doğru GUID
            
            # Projenin relative path'ini hesapla
            relative_path = os.path.relpath(csproj_path, solution_path.parent)
            relative_path = relative_path.replace('\\', '/')  # Path'i düzelt
            
            # Yeni proje tanımını oluştur
            project_entry = f'''Project("{{{vs_guid}}}") = "{project_name}", "tests/Tests/Tests.csproj", "{project_guid}"
EndProject'''
            
            # Global section'ı bul
            global_section_index = solution_content.find("Global")
            if global_section_index == -1:
                log_callback("Solution dosyasında Global section bulunamadı!", "error")
                return False
            
            # Proje tanımını ekle
            new_content = solution_content[:global_section_index] + project_entry + "\n" + solution_content[global_section_index:]
            
            # Solution configuration'a ekle
            config_pattern = r'GlobalSection\(ProjectConfigurationPlatforms\).*?EndGlobalSection'
            platform_section = re.search(config_pattern, new_content, re.DOTALL)
            if platform_section:
                platform_section_end = platform_section.end()
                project_config = f'''		{project_guid}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
		{project_guid}.Debug|Any CPU.Build.0 = Debug|Any CPU
		{project_guid}.Release|Any CPU.ActiveCfg = Release|Any CPU
		{project_guid}.Release|Any CPU.Build.0 = Release|Any CPU
'''
                new_content = new_content[:platform_section_end - len("EndGlobalSection")] + project_config + "EndGlobalSection" + new_content[platform_section_end:]
            
            # Değişiklikleri kaydet
            with open(solution_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            log_callback(f"Proje solution'a eklendi: {project_name}", "success")
            return True
            
        except Exception as e:
            log_callback(f"Proje solution'a eklenirken hata oluştu: {str(e)}", "error")
            return False

    def run_tests(self, test_project_path: Path, solution_path: Path, log_callback) -> dict:
        """Testleri çalıştırır ve sonuçları döndürür."""
        results = {}
        original_cwd = os.getcwd()
        
        try:
            solution_dir = solution_path.parent
            os.chdir(solution_dir)
            
            # Test projesini solution'a ekle
            if not self.add_project_to_solution(solution_path, test_project_path, log_callback):
                return results
            
            # Solution dosyasını parametre olarak ver
            log_callback("\nProje bağımlılıkları yükleniyor...")
            log_callback(f"Solution dizini: {solution_dir}")
            log_callback(f"Kullanılan solution: {solution_path}")
            log_callback(f"Test proje yolu: {test_project_path}")
            
            # Önce test projesini restore et
            log_callback("\nTest projesi restore ediliyor...")
            test_restore_result = subprocess.run(
                ["dotnet", "restore", str(test_project_path), "--verbosity", "detailed"],
                capture_output=True,
                text=True
            )
            
            if test_restore_result.stdout:
                log_callback("\nTest projesi restore çıktısı:", "info")
                log_callback(test_restore_result.stdout, "info")
            
            if test_restore_result.stderr:
                log_callback("\nTest projesi restore hata çıktısı:", "error")
                log_callback(test_restore_result.stderr, "error")
            
            # Sonra solution'ı restore et
            log_callback("\nSolution restore ediliyor...")
            restore_result = subprocess.run(
                ["dotnet", "restore", str(solution_path), "--verbosity", "detailed"],
                capture_output=True,
                text=True
            )
            
            if restore_result.stdout:
                log_callback("\nSolution restore çıktısı:", "info")
                log_callback(restore_result.stdout, "info")
            
            if restore_result.stderr:
                log_callback("\nSolution restore hata çıktısı:", "error")
                log_callback(restore_result.stderr, "error")
            
            if restore_result.returncode != 0:
                log_callback(f"\nRestore işlemi başarısız oldu. Hata kodu: {restore_result.returncode}", "error")
                # Proje referans yolunu kontrol et
                csproj_path = test_project_path / f"{test_project_path.name}.csproj"
                if csproj_path.exists():
                    with open(csproj_path, 'r', encoding='utf-8') as f:
                        csproj_content = f.read()
                        log_callback(f"\nTest proje dosyası içeriği:", "info")
                        log_callback(csproj_content, "info")
                return results
            else:
                log_callback("\nRestore işlemi başarılı!", "success")
            
            # Build işlemi için de solution dosyasını belirt
            log_callback("\nProje derleniyor...")
            build_result = subprocess.run(
                ["dotnet", "build", str(solution_path), "--no-restore", "-v:d"],
                capture_output=True,
                text=True
            )
            
            # Build çıktısını detaylı logla
            if build_result.stdout:
                log_callback("\nBuild çıktısı:", "info")
                log_callback(build_result.stdout, "info")
            
            if build_result.stderr:
                log_callback("\nBuild hata çıktısı:", "error")
                log_callback(build_result.stderr, "error")
            
            if build_result.returncode != 0:
                log_callback(f"\nDerleme başarısız oldu. Hata kodu: {build_result.returncode}", "error")
                return results
            else:
                log_callback("\nDerleme başarılı!", "success")
            
            # Test çalıştırma
            log_callback(f"\n{test_project_path.stem} projesinin testleri çalıştırılıyor...")
            
            # Detaylı test çıktısı için özel format kullan
            test_result = subprocess.run(
                [
                    "dotnet", "test", str(test_project_path),
                    "--no-build",
                    "--logger:trx",
                    "--logger:console;verbosity=detailed",
                    "--collect:\"XPlat Code Coverage\""
                ],
                capture_output=True,
                text=True
            )
            
            # Test sonuçlarını detaylı analiz et
            test_output = test_result.stdout
            test_error = test_result.stderr
            
            if test_output:
                # Test sonuçlarını parse et
                passed_tests = len(re.findall(r'Passed!', test_output))
                failed_tests = len(re.findall(r'Failed!', test_output))
                skipped_tests = len(re.findall(r'Skipped', test_output))
                
                # Test özetini oluştur
                summary = f"""
Test Sonuçları Özeti:
--------------------
Toplam Test Sayısı: {passed_tests + failed_tests + skipped_tests}
Başarılı: {passed_tests} ✅
Başarısız: {failed_tests} ❌
Atlanmış: {skipped_tests} ⚠️
"""
                log_callback(summary, "info")
                
                # Detaylı test çıktısı
                log_callback("\nDetaylı Test Çıktısı:", "info")
                log_callback(test_output, "info")
            
            if test_error:
                log_callback("\nTest Hataları:", "error")
                log_callback(test_error, "error")
            
            # Test sonuçlarını kaydet
            test_files = list(test_project_path.rglob("*.cs"))
            for test_file in test_files:
                if "Tests" in test_file.name:
                    results[str(test_file)] = {
                        "output": test_output,
                        "error": test_error if test_result.returncode != 0 else None,
                        "summary": {
                            "passed": passed_tests,
                            "failed": failed_tests,
                            "skipped": skipped_tests
                        }
                    }
            
        except Exception as e:
            log_callback(f"Test çalıştırma hatası: {str(e)}", "error")
            import traceback
            log_callback(traceback.format_exc(), "error")
        finally:
            os.chdir(original_cwd)
        
        return results
    
    def analyze_test_error(self, test_file: str, error_message: str, log_callback):
        """Test hatalarını analiz eder ve öneriler sunar."""
        # Test sonuçlarından mesajları ayıkla
        messages = []
        if isinstance(error_message, str):
            lines = error_message.split('\n')
            for line in lines:
                if "Message:" in line:
                    message_match = re.search(r'Message:\s+(.+)', line)
                    if message_match:
                        messages.append(message_match.group(1))
        
        # Analiz için mesajları birleştir
        error_details = "\n".join(messages) if messages else error_message
        
        prompt = f"""Analyze this C# test error and provide specific recommendations:

Test File: {test_file}
Error Details:
{error_details}

Please provide:
1. The root cause of the error (based on the error messages)
2. Specific suggestions to fix each error
3. If it's a syntax error, provide the corrected code snippet
4. If it's a logical error or assertion failure, explain the expected vs actual behavior
5. Recommendations for improving the test

Focus on actionable, specific advice based on the error messages."""

        response = ""
        for message in self.run_llm(prompt, is_analyzer=True):
            response += str(message)
        
        log_callback("\nHata Analizi:", "info")
        log_callback(response, "warning")
    
    def analyze_source_code(self, source_code: str) -> dict:
        """Kaynak koddan önemli bilgileri çıkarır."""
        # Namespace'i bul
        namespace_match = re.search(r'namespace\s+([\w\.]+)', source_code)
        namespace = namespace_match.group(1) if namespace_match else None

        # Using direktiflerini bul
        using_statements = re.findall(r'using\s+([\w\.]+);', source_code)

        # Sınıf adını bul
        class_match = re.search(r'public\s+class\s+(\w+)', source_code)
        class_name = class_match.group(1) if class_match else None

        # Constructor'ları bul
        constructor_pattern = fr'public\s+{class_name}\s*\((.*?)\)'
        constructors = []
        if class_name:
            constructor_matches = re.finditer(constructor_pattern, source_code, re.DOTALL)
            for match in constructor_matches:
                params = match.group(1).strip()
                constructors.append(params)

        # Public metodları bul
        method_pattern = r'public\s+(?:async\s+)?([\w<>[\]]+)\s+(\w+)\s*\((.*?)\)(?:\s*where\s+.*?)?(?:\s*{\s*.*?\s*}|\s*;)'
        methods = []
        for match in re.finditer(method_pattern, source_code, re.DOTALL):
            return_type = match.group(1)
            method_name = match.group(2)
            parameters = match.group(3).strip()
            methods.append({
                'name': method_name,
                'return_type': return_type,
                'parameters': parameters
            })

        # Interface ve dependency'leri bul
        interface_pattern = r'private\s+readonly\s+([\w<>]+)\s+\w+;'
        dependencies = re.findall(interface_pattern, source_code)

        return {
            'namespace': namespace,
            'using_statements': using_statements,
            'class_name': class_name,
            'constructors': constructors,
            'methods': methods,
            'dependencies': dependencies
        }

    def generate_and_fix_test(self, cs_file: Path, tests_proj_dir: Path, project_name: str, previous_errors: list, attempt: int, max_attempts: int, log_callback) -> tuple[bool, str]:
        """Test dosyasını oluşturur ve hatalara göre düzeltir."""
        if attempt > max_attempts:
            log_callback(f"Maksimum deneme sayısına ulaşıldı ({max_attempts}). Test oluşturma işlemi durduruldu.", "error")
            return False, None

        try:
            test_file_name = f"{cs_file.stem}UnitTest.cs"
            test_file_path = tests_proj_dir / test_file_name

            # Kaynak dosya içeriğini oku ve analiz et
            with open(cs_file, 'r', encoding='utf-8') as f:
                source_code = f.read()
            
            code_analysis = self.analyze_source_code(source_code)
            
            # İlk denemede veya dosya yoksa tüm kodu oluştur
            if attempt == 1 or not test_file_path.exists():
                error_context = ""
                if previous_errors:
                    error_context = "\nPrevious errors that need to be fixed:\n" + "\n".join(previous_errors)

                # Metod listesini oluştur
                method_details = []
                for method in code_analysis['methods']:
                    method_details.append(f"""Method: {method['name']}
Return Type: {method['return_type']}
Parameters: {method['parameters']}
""")
                methods_info = "\n".join(method_details)

                prompt = f"""IMPORTANT: Generate a COMPLETE C# test file with FULL implementation.

Source Code Analysis:
--------------------
Namespace: {code_analysis['namespace']}
Class: {code_analysis['class_name']}
Dependencies: {', '.join(code_analysis['dependencies'])}

Required Using Statements:
{chr(10).join(code_analysis['using_statements'])}

Constructor Parameters:
{chr(10).join(code_analysis['constructors'])}

Public Methods to Test:
{methods_info}

Source code:
{source_code}

{error_context}

REQUIREMENTS:
1. Use EXACTLY these using statements at the top:
   {chr(10).join(code_analysis['using_statements'])}
   using Xunit;
   using Moq;
   using FluentAssertions;

2. Create namespace: {project_name}.UnitTest

3. Create test class: {code_analysis['class_name']}UnitTest

4. Create constructor with these mock objects:
   {chr(10).join(f"private readonly Mock<{dep}> _mock{dep.replace('I', '')};" for dep in code_analysis['dependencies'])}

5. Initialize mocks in constructor:
   {chr(10).join(f"_mock{dep.replace('I', '')} = new Mock<{dep}>();" for dep in code_analysis['dependencies'])}

6. For each method, create these test scenarios:
   - MethodName_ValidInput_ReturnsExpectedResult
   - MethodName_InvalidInput_ThrowsException (if applicable)
   - MethodName_EdgeCase_HandlesCorrectly (if applicable)

7. Each test method MUST have:
   - [Fact] attribute
   - Proper async/await if testing async methods
   - Arrange section with mock setups
   - Act section calling the method
   - Assert section using FluentAssertions

8. Mock all external dependencies:
   {chr(10).join(f"_mock{dep.replace('I', '')}.Setup(...).Returns/ReturnsAsync(...);" for dep in code_analysis['dependencies'])}"""

            else:
                # Sonraki denemelerde mevcut kodu oku ve hataları düzelt
                with open(test_file_path, 'r', encoding='utf-8') as f:
                    existing_code = f.read()

                # Son 3 hatayı al
                error_details = "\n".join(previous_errors[-3:])

                # Hata mesajlarından test edilen metod adlarını bul
                method_names = set()
                for error in previous_errors:
                    # Metod adı kalıpları için regex'ler
                    patterns = [
                        r"The name '(\w+)' does not exist",
                        r"Cannot find method '(\w+)'",
                        r"'(\w+)' is inaccessible",
                        r"Method '(\w+)' not found",
                        r"(\w+)\s*\(.*?\) is not defined",
                        r"No overload for method '(\w+)'",
                        r"Cannot convert from '(\w+)' to '(\w+)'",
                        r"Argument (\d+): cannot convert from '(\w+)' to '(\w+)'",
                        r"'(\w+)' does not contain a definition for '(\w+)'",
                    ]
                    
                    for pattern in patterns:
                        matches = re.finditer(pattern, error, re.IGNORECASE)
                        for match in matches:
                            if match.lastindex == 1:
                                method_names.add(match.group(1))
                            else:
                                # Tip dönüşüm hatalarında her iki tipi de ekle
                                method_names.update(match.groups()[1:])

                # İlgili metodları bul
                relevant_methods = []
                for method in code_analysis['methods']:
                    if any(name in method['name'] for name in method_names):
                        relevant_methods.append(f"""Method: {method['name']}
Return Type: {method['return_type']}
Parameters: {method['parameters']}
""")

                relevant_info = "\n".join(relevant_methods) if relevant_methods else "// No specific methods found"
                
                prompt = f"""IMPORTANT: Fix the following build errors in the C# test file.

Current test code:
{existing_code}

Relevant method signatures:
{relevant_info}

Source code analysis:
--------------------
Namespace: {code_analysis['namespace']}
Class: {code_analysis['class_name']}
Dependencies: {', '.join(code_analysis['dependencies'])}

Build errors to fix:
{error_details}

Full source code for reference:
{source_code}

REQUIREMENTS:
1. Keep the existing code structure
2. Fix ONLY the specific build errors
3. Ensure all method signatures match exactly:
   - Parameter types must match source code
   - Return types must match source code
   - Async/await usage must be correct
4. Verify mock setup signatures match interface methods
5. Keep existing test methods and functionality
6. Ensure namespace and class names are correct
7. Fix any missing using statements or dependencies"""

            log_callback(f"\nTest kodu {attempt}. deneme {'oluşturuluyor' if attempt == 1 else 'düzeltiliyor'}...")
            start_time = time.time()

            # LLM'den yanıt al
            response = self.run_llm(prompt, is_analyzer=False)
            test_code = response.strip()

            # Markdown kod bloklarını ve gereksiz karakterleri temizle
            test_code = re.sub(r'^```csharp\s*', '', test_code)  # Başlangıç kod bloğunu temizle
            test_code = re.sub(r'\s*```$', '', test_code)        # Bitiş kod bloğunu temizle
            test_code = re.sub(r'```\s*$', '', test_code)        # Alternatif bitiş bloğunu temizle
            test_code = test_code.replace('`', '')               # Tek tırnak işaretlerini temizle
            
            # Boş satırları ve fazladan boşlukları temizle
            test_code = '\n'.join(line.rstrip() for line in test_code.splitlines() if line.strip())
            
            log_callback(f"Test kodu işlemi {time.time() - start_time:.2f} saniye sürdü")

            if not test_code:
                log_callback("Boş yanıt alındı, yeniden deneniyor...", "warning")
                return self.generate_and_fix_test(cs_file, tests_proj_dir, project_name, previous_errors, attempt + 1, max_attempts, log_callback)

            # Test kodunu kaydet
            with open(test_file_path, 'w', encoding='utf-8') as f:
                f.write(test_code)

            log_callback(f"Test kodu {'oluşturuldu' if attempt == 1 else 'düzeltildi'}: {test_file_path}", "success")
            return True, test_file_path

        except Exception as e:
            log_callback(f"Test kodu işlemi hatası: {str(e)}", "error")
            return False, None

    def generate_and_run_tests(self, source_path: str, log_callback) -> dict:
        """Testleri oluşturur, çalıştırır ve sonuçları analiz eder."""
        path = Path(source_path)
        cs_files = self.find_cs_files(path)
        test_results = {}
        max_attempts = 5  # Maksimum deneme sayısını 5'e çıkardık
        
        try:
            # Solution dosyasını bul
            solution_path = self.find_solution_file(path)
            solution_dir = solution_path.parent
            log_callback(f"Solution dosyası bulundu: {solution_path}", "success")
            
            # tests dizinini oluştur (solution dizini altında)
            tests_dir = solution_dir / "tests"
            tests_dir.mkdir(exist_ok=True)
            
            # Tests klasörü için proje oluştur
            tests_proj_dir = tests_dir / "Tests"
            tests_proj_dir.mkdir(exist_ok=True)
            
            # Test proje dosyasını oluştur (.csproj)
            csproj_path = tests_proj_dir / "Tests.csproj"
            if not csproj_path.exists():
                # Solution dizinindeki tüm .csproj dosyalarını bul
                project_references = []
                target_framework = None
                framework_versions = []
                
                try:
                    # Tüm .csproj dosyalarını bul
                    csproj_files = self.find_csproj_files(solution_dir)
                    log_callback(f"Bulunan .csproj dosyaları: {len(csproj_files)}", "info")
                    
                    for csproj_file in csproj_files:
                        # Proje referansını ekle
                        source_project_path = os.path.relpath(csproj_file, tests_proj_dir)
                        source_project_path = source_project_path.replace('\\', '/')
                        if source_project_path not in project_references:
                            project_references.append(source_project_path)
                            log_callback(f"Proje referansı eklendi: {source_project_path}", "info")
                            
                        # Framework bilgisini al
                        with open(csproj_file, 'r', encoding='utf-8') as f:
                            csproj_content = f.read()
                            framework_match = re.search(r'<TargetFramework>(.*?)</TargetFramework>', csproj_content)
                            if framework_match:
                                framework_version = framework_match.group(1)
                                framework_versions.append(framework_version)
                                log_callback(f"Proje framework'ü bulundu: {framework_version} ({csproj_file.name})", "info")
                except Exception as e:
                    log_callback(f"Framework bilgisi alınamadı: {str(e)}", "warning")
                
                # En düşük framework versiyonunu seç
                if framework_versions:
                    framework_versions.sort()
                    target_framework = framework_versions[0]
                    log_callback(f"Test projesi için seçilen framework: {target_framework}", "success")
                else:
                    target_framework = "net6.0"
                    log_callback("Framework bilgisi bulunamadı, varsayılan olarak net6.0 kullanılıyor.", "warning")
                
                # Proje referanslarını XML formatında oluştur
                project_refs_xml = "\n    ".join([f'<ProjectReference Include="{ref}" />' for ref in project_references])
                
                csproj_content = f"""<Project Sdk=\"Microsoft.NET.Sdk\">
  <PropertyGroup>
    <TargetFramework>{target_framework}</TargetFramework>
    <Nullable>enable</Nullable>
    <IsPackable>false</IsPackable>
    <RootNamespace>Tests</RootNamespace>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include=\"Microsoft.NET.Test.Sdk\" Version=\"17.9.0\" />
    <PackageReference Include=\"xunit\" Version=\"2.6.6\" />
    <PackageReference Include=\"xunit.runner.visualstudio\" Version=\"2.5.6\" />
    <PackageReference Include=\"coverlet.collector\" Version=\"6.0.0\" />
    <PackageReference Include=\"Moq\" Version=\"4.20.70\" />
    <PackageReference Include=\"FluentAssertions\" Version=\"6.12.0\" />
  </ItemGroup>

  <ItemGroup>
    {project_refs_xml}
  </ItemGroup>
</Project>"""
                with open(csproj_path, 'w', encoding='utf-8') as f:
                    f.write(csproj_content)
                log_callback(f"Test proje dosyası oluşturuldu: {csproj_path}", "success")
                log_callback(f"Proje referansları: {project_references}", "info")
            
            # Test projesini solution'a ekle
            if not self.add_project_to_solution(solution_path, tests_proj_dir, log_callback):
                log_callback("Test projesi solution'a eklenemedi!", "error")
                return test_results
            
            # Solution'ı restore et
            log_callback("\nSolution restore ediliyor...")
            restore_result = subprocess.run(
                ["dotnet", "restore", str(solution_path), "--verbosity", "detailed"],
                capture_output=True,
                text=True,
                cwd=solution_dir
            )
            
            if restore_result.returncode != 0:
                log_callback(f"\nRestore işlemi başarısız oldu. Hata kodu: {restore_result.returncode}", "error")
                if csproj_path.exists():
                    with open(csproj_path, 'r', encoding='utf-8') as f:
                        log_callback("\nTest proje dosyası içeriği:", "info")
                        log_callback(f.read(), "info")
                return test_results
            
            # Her kaynak dosya için test oluştur ve çalıştır
            for cs_file in cs_files:
                log_callback(f"\nTest oluşturuluyor: {cs_file}")
                
                # Recursive test oluşturma ve düzeltme işlemi
                file_results = self.build_and_test(
                    solution_path,
                    tests_proj_dir,
                    cs_file,
                    solution_dir,
                    max_attempts,
                    log_callback
                )
                
                test_results.update(file_results)
            
        except FileNotFoundError as e:
            log_callback(str(e), "error")
        
        return test_results

    def build_and_test(self, solution_path: Path, tests_proj_dir: Path, cs_file: Path, solution_dir: Path, max_attempts: int, log_callback) -> dict:
        """Build işlemini yapar ve hata durumunda testleri düzeltir."""
        attempt = 1
        previous_errors = []
        test_results = {}

        # İlk önce test dosyasını oluştur
        project_name = cs_file.parent.name or "Project"
        success, test_file_path = self.generate_and_fix_test(
            cs_file, 
            tests_proj_dir, 
            project_name, 
            previous_errors, 
            attempt, 
            max_attempts, 
            log_callback
        )

        if not success:
            log_callback("İlk test dosyası oluşturma başarısız oldu.", "error")
            return test_results

        while attempt <= max_attempts:
            # Build işlemini dene
            build_result = subprocess.run(
                ["dotnet", "build", str(solution_path), "--no-restore", "-v:d"],
                capture_output=True,
                text=True,
                cwd=solution_dir
            )

            if build_result.returncode == 0:
                log_callback("\nBuild başarılı!", "success")
                
                # Testleri çalıştır
                log_callback("\nTestler çalıştırılıyor...", "info")
                test_result = subprocess.run(
                    [
                        "dotnet", "test", str(tests_proj_dir),
                        "--no-build",
                        "--logger:trx",
                        "--logger:console;verbosity=detailed",
                        "--collect:\"XPlat Code Coverage\""
                    ],
                    capture_output=True,
                    text=True,
                    cwd=solution_dir
                )
                
                # Test çıktısını logla
                if test_result.stdout:
                    log_callback("\nTest Çıktısı:", "info")
                    log_callback(test_result.stdout, "info")
                
                if test_result.stderr:
                    log_callback("\nTest Hataları:", "error")
                    log_callback(test_result.stderr, "error")
                
                # Test sonuçlarını analiz et
                test_results = self.analyze_test_results(test_result, test_file_path, log_callback)
                
                if test_result.returncode == 0:
                    log_callback("\nTestler başarıyla tamamlandı!", "success")
                    return test_results
                else:
                    log_callback("\nBazı testler başarısız oldu.", "warning")
                    if attempt < max_attempts:
                        log_callback(f"\nTest hataları düzeltiliyor (Deneme {attempt}/{max_attempts})...", "info")
                        previous_errors.extend([test_result.stderr] if test_result.stderr else [])
                        attempt += 1
                        continue
                    else:
                        return test_results
            else:
                log_callback(f"\nBuild hatası (Deneme {attempt}/{max_attempts}):", "error")
                
                # Build hatalarını ayıkla ve analiz et
                error_messages = []
                error_locations = {}
                
                if build_result.stderr:
                    for line in build_result.stderr.split('\n'):
                        if "error" in line.lower():
                            # Hata mesajını ve konumunu ayıkla
                            error_match = re.search(r'(.*?)\((\d+),(\d+)\):\s*error\s+(\w+):\s*(.+)', line)
                            if error_match:
                                file_path, line_num, col_num, error_code, error_msg = error_match.groups()
                                error_messages.append({
                                    'file': file_path,
                                    'line': int(line_num),
                                    'column': int(col_num),
                                    'code': error_code,
                                    'message': error_msg.strip()
                                })
                                # Hata konumlarını grupla
                                if file_path not in error_locations:
                                    error_locations[file_path] = []
                                error_locations[file_path].append(int(line_num))
                            else:
                                error_messages.append({'message': line.strip()})
                            log_callback(line.strip(), "error")

                # Test dosyasının mevcut içeriğini oku
                with open(test_file_path, 'r', encoding='utf-8') as f:
                    current_test_code = f.read()

                # Hata analizi için LLM prompt'unu hazırla
                error_analysis = []
                for error in error_messages:
                    if isinstance(error, dict) and 'code' in error:
                        error_analysis.append(f"Error {error['code']} at line {error['line']}: {error['message']}")
                    else:
                        error_analysis.append(str(error.get('message', '')))

                # Kaynak dosyayı oku
                with open(cs_file, 'r', encoding='utf-8') as f:
                    source_code = f.read()

                # LLM'e gönderilecek prompt'u hazırla
                prompt = f"""IMPORTANT: Fix the following build errors in the C# test file.

Current test code with build errors:
{current_test_code}

Build Errors:
{chr(10).join(error_analysis)}

Source code being tested:
{source_code}

REQUIREMENTS:
1. Analyze each build error and provide specific fixes
2. Keep the existing test structure and functionality
3. Fix ONLY the problematic code sections
4. Ensure all method signatures match the source code exactly
5. Verify all dependencies and using statements
6. Optimize the code while fixing errors
7. Follow C# best practices and patterns
8. Maintain test coverage and assertions
9. Keep the code clean and maintainable

Return the complete corrected test code."""

                # LLM'den düzeltilmiş kodu al
                log_callback("\nBuild hataları analiz ediliyor ve düzeltiliyor...", "info")
                response = ""
                for message in self.run_llm(prompt):
                    response += str(message)

                # Markdown kod bloklarını ve gereksiz karakterleri temizle
                test_code = response.strip()
                test_code = re.sub(r'^```csharp\s*', '', test_code)
                test_code = re.sub(r'\s*```$', '', test_code)
                test_code = re.sub(r'```\s*$', '', test_code)
                test_code = test_code.replace('`', '')
                
                # Boş satırları ve fazladan boşlukları temizle
                test_code = '\n'.join(line.rstrip() for line in test_code.splitlines() if line.strip())

                # Düzeltilmiş kodu kaydet
                with open(test_file_path, 'w', encoding='utf-8') as f:
                    f.write(test_code)

                log_callback(f"Test kodu düzeltildi ve kaydedildi: {test_file_path}", "success")

                # Hataları previous_errors listesine ekle
                previous_errors.extend([str(error.get('message', '')) for error in error_messages])

                attempt += 1
                continue

        log_callback(f"\nMaksimum deneme sayısına ulaşıldı ({max_attempts}). İşlem durduruldu.", "error")
        return test_results

    def analyze_test_results(self, test_result, test_file_path, log_callback) -> dict:
        """Test sonuçlarını analiz eder ve raporlar."""
        # Test çıktısından hata mesajlarını ayıkla
        error_messages = []
        if test_result.stderr:
            error_lines = test_result.stderr.split('\n')
            for line in error_lines:
                if "error" in line.lower():
                    error_match = re.search(r'error\s+(\w+\d+):\s+(.+)', line, re.IGNORECASE)
                    if error_match:
                        error_code = error_match.group(1)
                        error_message = error_match.group(2)
                        error_messages.append(f"Hata Kodu: {error_code}\nMesaj: {error_message}")

        # Test sonuçlarını detaylı analiz et
        test_output = test_result.stdout
        test_messages = []

        if test_output:
            output_lines = test_output.split('\n')
            for line in output_lines:
                if any(keyword in line for keyword in ['Failed', 'Passed', 'Skipped']):
                    test_match = re.search(r'([\w\.]+)\s+(Failed|Passed|Skipped)', line)
                    if test_match:
                        test_name = test_match.group(1)
                        test_result_status = test_match.group(2)
                        test_messages.append(f"{test_name}: {test_result_status}")

                if "Message:" in line:
                    message_match = re.search(r'Message:\s+(.+)', line)
                    if message_match:
                        test_messages.append(f"Hata Detayı: {message_match.group(1)}")

        # Test sonuçlarını logla
        if test_messages:
            log_callback("\nTest Sonuç Mesajları:", "info")
            for msg in test_messages:
                level = "error" if "Failed" in msg else "success" if "Passed" in msg else "warning"
                log_callback(msg, level)

        if error_messages:
            log_callback("\nHata Mesajları:", "error")
            for error in error_messages:
                log_callback(error, "error")

        return {
            str(test_file_path): {
                "output": test_output,
                "error": test_result.stderr if test_result.returncode != 0 else None,
                "messages": test_messages,
                "error_messages": error_messages
            }
        }

def main():
    app = TestGeneratorGUI()
    app.root.mainloop()

if __name__ == "__main__":
    main()